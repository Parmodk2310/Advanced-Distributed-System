import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_three_nodes_bootstrap_to_same_alive_membership(unused_tcp_port_factory):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    node0 = DistributedNode(cluster_settings(node_id="node-0", port=ports[0]))
    node1 = DistributedNode(
        cluster_settings(
            node_id="node-1",
            port=ports[1],
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        )
    )
    node2 = DistributedNode(
        cluster_settings(
            node_id="node-2",
            port=ports[2],
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        )
    )
    nodes = [node0, node1, node2]
    try:
        for node in nodes:
            await node.start()

        async def converged() -> bool:
            for node in nodes:
                assert node.cluster_service is not None
                snapshot = await node.cluster_service.membership.snapshot()
                if len(snapshot) != 3:
                    return False
                if any(member.status is not MemberStatus.ALIVE for member in snapshot):
                    return False
            return True

        await wait_until(converged)
    finally:
        for node in reversed(nodes):
            await node.stop()
