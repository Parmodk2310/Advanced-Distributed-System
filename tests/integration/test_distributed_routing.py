import pytest

from distsys.client import DistributedClient
from distsys.cluster.member import SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_keyed_request_executes_on_calculated_remote_owner(unused_tcp_port_factory):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    nodes = [
        DistributedNode(cluster_settings(node_id="node-0", port=ports[0])),
        DistributedNode(
            cluster_settings(
                node_id="node-1",
                port=ports[1],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
        DistributedNode(
            cluster_settings(
                node_id="node-2",
                port=ports[2],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
    ]
    try:
        for node in nodes:
            await node.start()

        async def converged() -> bool:
            for node in nodes:
                service = node.cluster_service
                if service is None or len(await service.membership.alive_members()) != 3:
                    return False
            return True

        await wait_until(converged)
        service = nodes[0].cluster_service
        assert service is not None
        key = next(
            f"customer-{i}"
            for i in range(10_000)
            if service.ring.owner(f"customer-{i}").node_id != "node-0"
        )
        expected_owner = service.ring.owner(key).node_id
        client = DistributedClient(port=ports[0])
        result = await client.request("cluster.whoami", {}, routing_key=key)
        assert result == {"node_id": expected_owner}
    finally:
        for node in reversed(nodes):
            await node.stop()
