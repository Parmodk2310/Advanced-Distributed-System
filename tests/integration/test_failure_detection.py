import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_stopped_node_transitions_to_suspect_then_dead(unused_tcp_port_factory):
    p0, p1 = [unused_tcp_port_factory() for _ in range(2)]
    node0 = DistributedNode(cluster_settings(node_id="node-0", port=p0))
    node1 = DistributedNode(
        cluster_settings(
            node_id="node-1",
            port=p1,
            seeds=(SeedAddress("127.0.0.1", p0),),
        )
    )
    try:
        await node0.start()
        await node1.start()
        assert node0.cluster_service is not None

        async def joined() -> bool:
            return await node0.cluster_service.membership.get("node-1") is not None

        await wait_until(joined)
        await node1.stop()

        async def suspect() -> bool:
            current = await node0.cluster_service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.SUSPECT

        await wait_until(suspect, timeout_seconds=2.0)
        assert all(
            member.node_id != "node-1"
            for member in node0.cluster_service.ring.candidates("any-key")
        )

        async def dead() -> bool:
            current = await node0.cluster_service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.DEAD

        await wait_until(dead, timeout_seconds=3.0)
    finally:
        await node1.stop()
        await node0.stop()
