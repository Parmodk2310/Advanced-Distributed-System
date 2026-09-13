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
        crdt_anti_entropy_interval_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_second_read_never_moves_behind_first_read_token(unused_tcp_port_factory):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    node0 = DistributedNode(settings(node_id="node-0", port=ports[0]))
    node1 = DistributedNode(
        settings(
            node_id="node-1",
            port=ports[1],
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        )
    )
    nodes = [node0, node1]
    try:
        for node in nodes:
            await node.start()

        async def ready():
            for node in nodes:
                if node.cluster_service is None:
                    return False
                snap = await node.cluster_service.membership.snapshot()
                if len(snap) != 2 or any(m.status is not MemberStatus.ALIVE for m in snap):
                    return False
            return True

        await wait_until(ready)

        writer = CrdtClient(port=ports[0], timeout_seconds=2)
        first_write = await writer.increment("reads", amount=1)
        first_read = await CrdtClient(port=ports[0], timeout_seconds=2).read(
            "reads", causal_token=first_write.causal_token
        )
        second_read = await CrdtClient(port=ports[1], timeout_seconds=2).read(
            "reads", causal_token=first_read.causal_token
        )
        assert second_read.value >= first_read.value
        assert second_read.causal_token.version.dominates(first_read.causal_token.version)
    finally:
        for node in reversed(nodes):
            await node.stop()
