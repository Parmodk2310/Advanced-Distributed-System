from dataclasses import replace

import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.crdt import CrdtType
from distsys.crdt_client import CrdtClient
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


def settings(*, node_id: str, port: int, seeds=()):
    return replace(
        cluster_settings(node_id=node_id, port=port, seeds=seeds),
        crdt_enabled=True,
        crdt_replication_factor=2,
        crdt_anti_entropy_interval_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_later_write_causally_dominates_earlier_write(unused_tcp_port_factory):
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
                if node.cluster_service is None:
                    return False
                snap = await node.cluster_service.membership.snapshot()
                if len(snap) != 2 or any(m.status is not MemberStatus.ALIVE for m in snap):
                    return False
            return True

        await wait_until(ready)

        first = await CrdtClient(port=ports[0], timeout_seconds=2).increment(
            "balance", amount=5, crdt_type=CrdtType.PNCOUNTER
        )
        second = await CrdtClient(port=ports[1], timeout_seconds=2).increment(
            "balance", amount=2, crdt_type=CrdtType.PNCOUNTER, causal_token=first.causal_token
        )
        assert second.value == 7
        assert second.causal_token.version.dominates(first.causal_token.version)
    finally:
        for node in reversed(nodes):
            await node.stop()
