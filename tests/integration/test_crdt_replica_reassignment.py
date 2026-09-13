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
        crdt_replication_factor=2,
        crdt_replication_workers=1,
        crdt_anti_entropy_interval_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_new_replica_receives_state_after_membership_reassignment(
    unused_tcp_port_factory,
):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    nodes = [
        DistributedNode(settings(node_id="node-0", port=ports[0])),
        DistributedNode(
            settings(
                node_id="node-1",
                port=ports[1],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
        DistributedNode(
            settings(
                node_id="node-2",
                port=ports[2],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
    ]
    stopped = None
    try:
        for node in nodes:
            await node.start()

        async def ready():
            for node in nodes:
                if node.cluster_service is None or node.crdt_service is None:
                    return False
                snap = await node.cluster_service.membership.snapshot()
                if len(snap) != 3 or any(m.status is not MemberStatus.ALIVE for m in snap):
                    return False
            return True

        await wait_until(ready)

        assert nodes[0].crdt_service is not None
        key = ""
        for i in range(5000):
            candidate = f"move-{i}"
            ids = {
                m.node_id for m in nodes[0].crdt_service.replication.selector.replicas(candidate)
            }
            if ids == {"node-0", "node-1"}:
                key = candidate
                break
        assert key
        result = await CrdtClient(port=ports[0], timeout_seconds=2).increment(key, amount=4)
        assert result.value == 4

        async def original_replicas_ready():
            for index in (0, 1):
                assert nodes[index].crdt_service is not None
                entry = await nodes[index].crdt_service.store.get(key)
                if entry is None or entry.state.value() != 4:
                    return False
            assert nodes[2].crdt_service is not None
            return await nodes[2].crdt_service.store.get(key) is None

        await wait_until(original_replicas_ready)

        stopped = nodes[1]
        await stopped.stop()

        async def reassigned():
            for node in (nodes[0], nodes[2]):
                assert node.cluster_service is not None
                snap = await node.cluster_service.membership.snapshot()
                status = next((m.status for m in snap if m.node_id == "node-1"), MemberStatus.DEAD)
                if status is MemberStatus.ALIVE:
                    return False
                assert node.crdt_service is not None
                ids = {m.node_id for m in node.crdt_service.replication.selector.replicas(key)}
                if ids != {"node-0", "node-2"}:
                    return False
            return True

        await wait_until(reassigned, timeout_seconds=2.0)

        assert nodes[0].crdt_service is not None
        await nodes[0].crdt_service.replication.anti_entropy.run_once()
        assert nodes[2].crdt_service is not None
        moved = await nodes[2].crdt_service.store.get(key)
        assert moved is not None and moved.state.value() == 4
    finally:
        for node in reversed(nodes):
            if node is stopped:
                continue
            await node.stop()
