from dataclasses import replace

import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.crdt_client import CrdtClient
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


def settings(*, node_id: str, port: int, seeds=()):
    return replace(
        cluster_settings(node_id=node_id, port=port, seeds=seeds),
        crdt_enabled=True,
        crdt_replication_factor=3,
        crdt_replication_workers=1,
        crdt_anti_entropy_interval_seconds=0.05,
        crdt_anti_entropy_batch_size=100,
    )


@pytest.mark.asyncio
async def test_rejoined_node_gets_new_actor_and_reconstructs_empty_store(
    unused_tcp_port_factory,
):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    base_settings = [
        settings(node_id="node-0", port=ports[0]),
        settings(node_id="node-1", port=ports[1], seeds=(SeedAddress("127.0.0.1", ports[0]),)),
        settings(node_id="node-2", port=ports[2], seeds=(SeedAddress("127.0.0.1", ports[0]),)),
    ]
    node0, node1, node2 = [DistributedNode(item) for item in base_settings]
    live = [node0, node1, node2]
    restarted = None
    try:
        for node in live:
            await node.start()

        async def three_ready(nodes):
            for node in nodes:
                if node.cluster_service is None or node.crdt_service is None:
                    return False
                snap = await node.cluster_service.membership.snapshot()
                if len(snap) != 3 or any(m.status is not MemberStatus.ALIVE for m in snap):
                    return False
            return True

        await wait_until(lambda: three_ready(live))
        initial = await CrdtClient(port=ports[0], timeout_seconds=2).increment("rejoin.views")

        async def all_have_one():
            for node in live:
                assert node.crdt_service is not None
                entry = await node.crdt_service.store.get("rejoin.views")
                if entry is None or entry.state.value() != 1:
                    return False
            return True

        await wait_until(all_have_one)

        assert node2.crdt_service is not None
        old_actor = node2.crdt_service.actor
        await node2.stop()
        live = [node0, node1]

        async def node2_not_alive():
            for node in live:
                assert node.cluster_service is not None
                snap = await node.cluster_service.membership.snapshot()
                status = next((m.status for m in snap if m.node_id == "node-2"), MemberStatus.DEAD)
                if status is MemberStatus.ALIVE:
                    return False
            return True

        await wait_until(node2_not_alive, timeout_seconds=2.0)

        updated = await CrdtClient(port=ports[0], timeout_seconds=2).increment(
            "rejoin.views", amount=2, causal_token=initial.causal_token
        )
        assert updated.value == 3

        restarted = DistributedNode(base_settings[2])
        await restarted.start()
        assert restarted.crdt_service is not None
        new_actor = restarted.crdt_service.actor
        assert new_actor.node_id == old_actor.node_id
        assert new_actor.incarnation != old_actor.incarnation
        assert await restarted.crdt_service.store.get("rejoin.views") is None

        full = [node0, node1, restarted]
        await wait_until(lambda: three_ready(full), timeout_seconds=3.0)

        async def recovered():
            assert restarted is not None and restarted.crdt_service is not None
            entry = await restarted.crdt_service.store.get("rejoin.views")
            return entry is not None and entry.state.value() == 3

        await wait_until(recovered, timeout_seconds=3.0)
    finally:
        if restarted is not None:
            await restarted.stop()
        for node in reversed(live):
            await node.stop()
