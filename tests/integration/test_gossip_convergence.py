import pytest

from distsys.cluster.member import SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_seed_learns_about_node_joined_through_another_member(
    unused_tcp_port_factory,
):
    p0, p1, p2 = [unused_tcp_port_factory() for _ in range(3)]
    node0 = DistributedNode(cluster_settings(node_id="node-0", port=p0))
    node1 = DistributedNode(
        cluster_settings(
            node_id="node-1",
            port=p1,
            seeds=(SeedAddress("127.0.0.1", p0),),
        )
    )
    node2 = DistributedNode(
        cluster_settings(
            node_id="node-2",
            port=p2,
            seeds=(SeedAddress("127.0.0.1", p1),),
        )
    )
    nodes = [node0, node1, node2]
    try:
        for node in nodes:
            await node.start()

        async def node0_knows_node2() -> bool:
            assert node0.cluster_service is not None
            return await node0.cluster_service.membership.get("node-2") is not None

        await wait_until(node0_knows_node2)
    finally:
        for node in reversed(nodes):
            await node.stop()
