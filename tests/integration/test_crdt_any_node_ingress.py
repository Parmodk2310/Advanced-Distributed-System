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
        crdt_anti_entropy_interval_seconds=1.0,
    )


@pytest.mark.asyncio
async def test_non_replica_ingress_forwards_once_to_authoritative_replica(
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
    try:
        for node in nodes:
            await node.start()

        async def ready() -> bool:
            for node in nodes:
                if node.cluster_service is None or node.crdt_service is None:
                    return False
                snapshot = await node.cluster_service.membership.snapshot()
                if len(snapshot) != 3 or any(m.status is not MemberStatus.ALIVE for m in snapshot):
                    return False
            return True

        await wait_until(ready)
        assert nodes[0].crdt_service is not None

        key = next(
            candidate
            for index in range(1000)
            if not nodes[0].crdt_service.replication.selector.is_replica(
                "node-0", candidate := f"non-local-{index}"
            )
        )
        replica_ids = {
            member.node_id for member in nodes[0].crdt_service.replication.selector.replicas(key)
        }
        assert "node-0" not in replica_ids

        result = await CrdtClient(port=ports[0], timeout_seconds=2).increment(key)
        assert result.value == 1
        assert result.served_by in replica_ids

        async def replicated_to_authoritative_set() -> bool:
            for node in nodes:
                assert node.crdt_service is not None
                entry = await node.crdt_service.store.get(key)
                if node.settings.node_id in replica_ids and (
                    entry is None or entry.state.value() != 1
                ):
                    return False
            return True

        await wait_until(replicated_to_authoritative_set)
    finally:
        for node in reversed(nodes):
            await node.stop()
