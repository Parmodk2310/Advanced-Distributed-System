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
        crdt_anti_entropy_batch_size=100,
    )


@pytest.mark.asyncio
async def test_digest_anti_entropy_repairs_state_missed_by_fast_replication(
    unused_tcp_port_factory,
):
    ports = [unused_tcp_port_factory() for _ in range(2)]
    nodes = [
        DistributedNode(settings(node_id="node-0", port=ports[0])),
        DistributedNode(
            settings(
                node_id="node-1",
                port=ports[1],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
    ]
    try:
        for node in nodes:
            await node.start()

        async def ready():
            for node in nodes:
                if node.cluster_service is None or node.crdt_service is None:
                    return False
                snap = await node.cluster_service.membership.snapshot()
                if len(snap) != 2 or any(m.status is not MemberStatus.ALIVE for m in snap):
                    return False
            return True

        await wait_until(ready)

        for node in nodes:
            assert node.crdt_service is not None
            await node.crdt_service.replication.stop()

        await CrdtClient(port=ports[0], timeout_seconds=2).increment("missed", amount=5)
        assert nodes[1].crdt_service is not None
        assert await nodes[1].crdt_service.store.get("missed") is None

        # Node-1 has an empty digest. Its only relevant peer reports the remote-only
        # key, after which node-1 selectively fetches and merges that state.
        await nodes[1].crdt_service.replication.anti_entropy.run_once()
        repaired = await nodes[1].crdt_service.store.get("missed")
        assert repaired is not None
        assert repaired.state.value() == 5
    finally:
        for node in reversed(nodes):
            await node.stop()
