from dataclasses import replace

import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.crdt_client import CrdtClient
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


def settings(*, node_id: str, port: int, seeds=()):
    return replace(
        cluster_settings(node_id=node_id, port=port, seeds=seeds),
        request_timeout_seconds=5.0,
        crdt_enabled=True,
        crdt_replication_factor=3,
        crdt_anti_entropy_interval_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_write_after_read_carries_read_causal_frontier(unused_tcp_port_factory):
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
    try:
        for node in nodes:
            await node.start()

        async def ready():
            for node in nodes:
                if node.cluster_service is None:
                    return False
                snap = await node.cluster_service.membership.snapshot()
                if len(snap) != 3 or any(m.status is not MemberStatus.ALIVE for m in snap):
                    return False
            return True

        await wait_until(ready)

        created = await CrdtClient(port=ports[0], timeout_seconds=2).add("source.tags", "python")
        observed = await CrdtClient(port=ports[1], timeout_seconds=2).read(
            "source.tags", causal_token=created.causal_token
        )
        derived = await CrdtClient(port=ports[2], timeout_seconds=2).increment(
            "derived.views", causal_token=observed.causal_token
        )
        assert derived.causal_token.version.dominates(observed.causal_token.version)
        assert nodes[2].crdt_service is not None
        entry = await nodes[2].crdt_service.store.get("derived.views")
        assert entry is not None
        assert entry.causal_context.dominates(observed.causal_token.version)
    finally:
        for node in reversed(nodes):
            await node.stop()
