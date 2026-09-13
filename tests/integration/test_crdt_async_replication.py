from dataclasses import replace

import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.crdt_client import CrdtClient
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


def crdt_settings(*, node_id: str, port: int, seeds=()):
    return replace(
        cluster_settings(node_id=node_id, port=port, seeds=seeds),
        crdt_enabled=True,
        crdt_replication_factor=3,
        crdt_replication_queue_capacity=100,
        crdt_replication_workers=1,
        crdt_replication_retry_max_attempts=2,
        crdt_replication_retry_base_delay_seconds=0.001,
        crdt_replication_retry_max_delay_seconds=0.002,
        crdt_anti_entropy_interval_seconds=0.05,
        crdt_anti_entropy_batch_size=100,
    )


@pytest.mark.asyncio
async def test_gcounter_state_replicates_to_three_node_replica_set(unused_tcp_port_factory):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    nodes = [
        DistributedNode(crdt_settings(node_id="node-0", port=ports[0])),
        DistributedNode(
            crdt_settings(
                node_id="node-1",
                port=ports[1],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
        DistributedNode(
            crdt_settings(
                node_id="node-2",
                port=ports[2],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
    ]
    try:
        for node in nodes:
            await node.start()

        async def cluster_ready() -> bool:
            for node in nodes:
                if node.cluster_service is None:
                    return False
                snapshot = await node.cluster_service.membership.snapshot()
                if len(snapshot) != 3 or any(
                    member.status is not MemberStatus.ALIVE for member in snapshot
                ):
                    return False
            return all(node.crdt_service is not None for node in nodes)

        await wait_until(cluster_ready)

        result = await CrdtClient(port=ports[0], timeout_seconds=2).increment(
            "page.views", amount=3
        )
        assert result.value == 3

        async def replicated() -> bool:
            entries = []
            for node in nodes:
                assert node.crdt_service is not None
                entry = await node.crdt_service.store.get("page.views")
                entries.append(entry)
            return all(entry is not None and entry.state.value() == 3 for entry in entries)

        await wait_until(replicated, timeout_seconds=2.0)
    finally:
        for node in reversed(nodes):
            await node.stop()
