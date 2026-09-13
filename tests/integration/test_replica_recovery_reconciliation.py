from dataclasses import replace

import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.crdt_client import CrdtClient
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


def durable_settings(*, node_id: str, port: int, db_path: str, seeds=()):
    return replace(
        cluster_settings(node_id=node_id, port=port, seeds=seeds),
        crdt_enabled=True,
        crdt_replication_factor=3,
        crdt_replication_workers=1,
        crdt_anti_entropy_interval_seconds=0.05,
        crdt_anti_entropy_batch_size=100,
        persistence_enabled=True,
        persistence_db_path=db_path,
        etcd_enabled=False,
        tls_enabled=False,
    )


@pytest.mark.asyncio
async def test_stale_durable_replica_reconciles_after_restart(
    unused_tcp_port_factory,
    tmp_path,
):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    settings = [
        durable_settings(
            node_id="node-0",
            port=ports[0],
            db_path=str(tmp_path / "node-0.db"),
        ),
        durable_settings(
            node_id="node-1",
            port=ports[1],
            db_path=str(tmp_path / "node-1.db"),
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        ),
        durable_settings(
            node_id="node-2",
            port=ports[2],
            db_path=str(tmp_path / "node-2.db"),
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        ),
    ]
    node0, node1, node2 = [DistributedNode(item) for item in settings]
    restarted = None
    live = [node0, node1, node2]
    try:
        for node in live:
            await node.start()

        async def three_ready(nodes) -> bool:
            for node in nodes:
                if node.cluster_service is None or node.crdt_service is None:
                    return False
                snap = await node.cluster_service.membership.snapshot()
                if {m.node_id for m in snap if m.status is MemberStatus.ALIVE} != {
                    "node-0",
                    "node-1",
                    "node-2",
                }:
                    return False
            return True

        await wait_until(lambda: three_ready(live), timeout_seconds=3.0)

        client = CrdtClient(port=ports[0], timeout_seconds=2.0)
        initial = await client.increment("durable.reconcile")
        assert initial.value == 1

        async def all_have_one() -> bool:
            for node in live:
                assert node.crdt_service is not None
                entry = await node.crdt_service.store.get("durable.reconcile")
                if entry is None or entry.state.value() != 1:
                    return False
            return True

        await wait_until(all_have_one, timeout_seconds=2.0)

        assert node2.crdt_service is not None
        assert node2.cluster_service is not None
        old_actor = node2.crdt_service.actor
        old_swim_incarnation = node2.cluster_service.local_member.incarnation
        old_frontier = await node2.crdt_service.clock.frontier()
        old_counter = old_frontier.get(old_actor)

        await node2.stop()
        live = [node0, node1]

        async def node2_not_alive() -> bool:
            for node in live:
                assert node.cluster_service is not None
                member = await node.cluster_service.membership.get("node-2")
                if member is not None and member.status is MemberStatus.ALIVE:
                    return False
            return True

        await wait_until(node2_not_alive, timeout_seconds=3.0)

        advanced = await client.increment(
            "durable.reconcile",
            amount=2,
            causal_token=initial.causal_token,
        )
        assert advanced.value == 3

        restarted = DistributedNode(settings[2])
        await restarted.start()
        assert restarted.crdt_service is not None
        assert restarted.cluster_service is not None
        assert restarted.crdt_service.actor == old_actor
        assert restarted.cluster_service.local_member.incarnation != old_swim_incarnation
        restored_frontier = await restarted.crdt_service.clock.frontier()
        assert restored_frontier.get(old_actor) >= old_counter

        full = [node0, node1, restarted]
        await wait_until(lambda: three_ready(full), timeout_seconds=3.0)

        async def converged() -> bool:
            for node in full:
                assert node.crdt_service is not None
                entry = await node.crdt_service.store.get("durable.reconcile")
                if entry is None or entry.state.value() != 3:
                    return False
            return True

        await wait_until(converged, timeout_seconds=3.0)
    finally:
        if restarted is not None:
            await restarted.stop()
        for node in reversed(live):
            await node.stop()
