import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_restarted_node_with_newer_incarnation_rejoins(unused_tcp_port_factory):
    p0, p1 = [unused_tcp_port_factory() for _ in range(2)]
    node0 = DistributedNode(cluster_settings(node_id="node-0", port=p0))
    node1 = DistributedNode(
        cluster_settings(
            node_id="node-1",
            port=p1,
            seeds=(SeedAddress("127.0.0.1", p0),),
        )
    )
    restarted = None
    try:
        await node0.start()
        await node1.start()
        service = node0.cluster_service
        assert service is not None

        async def joined() -> bool:
            return await service.membership.get("node-1") is not None

        await wait_until(joined)
        original = await service.membership.get("node-1")
        assert original is not None
        old_incarnation = original.incarnation
        await node1.stop()

        async def dead() -> bool:
            current = await service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.DEAD

        await wait_until(dead, timeout_seconds=3.0)

        restarted = DistributedNode(
            cluster_settings(
                node_id="node-1",
                port=p1,
                seeds=(SeedAddress("127.0.0.1", p0),),
            )
        )
        await restarted.start()

        async def rejoined() -> bool:
            current = await service.membership.get("node-1")
            return (
                current is not None
                and current.status is MemberStatus.ALIVE
                and current.incarnation > old_incarnation
            )

        await wait_until(rejoined, timeout_seconds=2.0)
    finally:
        if restarted is not None:
            await restarted.stop()
        await node1.stop()
        await node0.stop()
