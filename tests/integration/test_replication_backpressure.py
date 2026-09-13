from dataclasses import replace

import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.crdt_client import CrdtClient, RemoteCrdtError
from distsys.node import DistributedNode
from distsys.proto import messages_pb2
from tests.integration.cluster_helpers import cluster_settings, wait_until


def settings(*, node_id: str, port: int, seeds=()):
    return replace(
        cluster_settings(node_id=node_id, port=port, seeds=seeds),
        crdt_enabled=True,
        crdt_replication_factor=3,
        crdt_replication_queue_capacity=1,
        crdt_replication_workers=1,
        crdt_anti_entropy_interval_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_replication_backpressure_rejects_before_local_mutation(
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
        with pytest.raises(RemoteCrdtError) as exc:
            await CrdtClient(port=ports[0], timeout_seconds=2).increment("too-many-replicas")
        assert exc.value.code == messages_pb2.REPLICATION_BACKPRESSURE
        assert nodes[0].crdt_service is not None
        assert await nodes[0].crdt_service.store.get("too-many-replicas") is None
    finally:
        for node in reversed(nodes):
            await node.stop()
