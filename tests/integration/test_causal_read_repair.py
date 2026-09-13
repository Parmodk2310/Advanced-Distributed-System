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
        crdt_anti_entropy_interval_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_stale_replica_repairs_to_client_causal_frontier_before_read(
    unused_tcp_port_factory,
):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    node0 = DistributedNode(settings(node_id="node-0", port=ports[0]))
    node1 = DistributedNode(
        settings(
            node_id="node-1",
            port=ports[1],
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        )
    )
    node2 = DistributedNode(
        settings(
            node_id="node-2",
            port=ports[2],
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        )
    )
    nodes = [node0, node1, node2]
    started = []
    try:
        await node0.start()
        started.append(node0)
        await node1.start()
        started.append(node1)

        async def two_ready() -> bool:
            for node in (node0, node1):
                assert node.cluster_service is not None
                snapshot = await node.cluster_service.membership.snapshot()
                if len(snapshot) != 2 or any(
                    member.status is not MemberStatus.ALIVE for member in snapshot
                ):
                    return False
            return True

        await wait_until(two_ready)

        writer = CrdtClient(port=ports[0], timeout_seconds=2)
        written = await writer.add("user.tags", "python")
        assert written.value == ["python"]

        await node2.start()
        started.append(node2)

        async def three_ready() -> bool:
            for node in nodes:
                if node.cluster_service is None or node.crdt_service is None:
                    return False
                snapshot = await node.cluster_service.membership.snapshot()
                if len(snapshot) != 3 or any(
                    member.status is not MemberStatus.ALIVE for member in snapshot
                ):
                    return False
            return True

        await wait_until(three_ready)
        assert node2.crdt_service is not None
        assert await node2.crdt_service.store.get("user.tags") is None

        reader = CrdtClient(port=ports[2], timeout_seconds=2)
        repaired = await reader.read(
            "user.tags",
            causal_token=written.causal_token,
        )
        assert repaired.value == ["python"]
        assert repaired.served_by == "node-2"
        assert repaired.repair_performed is True
        assert repaired.causal_token.version.dominates(written.causal_token.version)
        assert await node2.crdt_service.store.get("user.tags") is not None
    finally:
        for node in reversed(started):
            await node.stop()


@pytest.mark.asyncio
async def test_unreachable_causal_frontier_returns_causal_unavailable(
    unused_tcp_port_factory,
):
    from distsys.causal import CausalActor, CausalToken, VersionVector
    from distsys.crdt_client import RemoteCrdtError
    from distsys.proto import messages_pb2

    ports = [unused_tcp_port_factory() for _ in range(2)]
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

        async def ready() -> bool:
            for node in nodes:
                assert node.cluster_service is not None
                if len(await node.cluster_service.membership.snapshot()) != 2:
                    return False
            return True

        await wait_until(ready)
        created = await CrdtClient(port=ports[0], timeout_seconds=2).increment("known")
        impossible = CausalToken(
            created.causal_token.version.merge(VersionVector({CausalActor("never-seen", 999): 7}))
        )
        with pytest.raises(RemoteCrdtError) as exc:
            await CrdtClient(port=ports[1], timeout_seconds=2).read(
                "known", causal_token=impossible
            )
        assert exc.value.code == messages_pb2.CAUSAL_UNAVAILABLE
    finally:
        for node in reversed(nodes):
            await node.stop()
