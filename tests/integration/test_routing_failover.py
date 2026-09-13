import pytest

from distsys.client import DistributedClient
from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_failed_primary_owner_is_removed_and_next_candidate_executes(unused_tcp_port_factory):
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
        service = nodes[0].cluster_service
        assert service is not None

        async def converged() -> bool:
            return len(await service.membership.alive_members()) == 3

        await wait_until(converged)
        key = next(
            f"failover-{i}"
            for i in range(10_000)
            if service.ring.owner(f"failover-{i}").node_id == "node-2"
        )
        client = DistributedClient(port=ports[0])
        assert await client.request("cluster.whoami", {}, routing_key=key) == {"node_id": "node-2"}

        await nodes[2].stop()

        async def removed_from_ownership() -> bool:
            current = await service.membership.get("node-2")
            if current is None or current.status is MemberStatus.ALIVE:
                return False
            return service.ring.owner(key).node_id != "node-2"

        await wait_until(removed_from_ownership, timeout_seconds=2.0)
        result = await client.request("cluster.whoami", {}, routing_key=key)
        assert result["node_id"] in {"node-0", "node-1"}
    finally:
        for node in reversed(nodes):
            await node.stop()
