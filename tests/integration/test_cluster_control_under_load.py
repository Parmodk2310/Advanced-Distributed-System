import pytest

from distsys.client import DistributedClient, RemoteTaskError
from distsys.cluster.member import SeedAddress
from distsys.node import DistributedNode
from distsys.proto import messages_pb2
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_ping_still_works_after_public_rate_limit_rejects_task(unused_tcp_port_factory):
    p0, p1 = [unused_tcp_port_factory() for _ in range(2)]
    node0 = DistributedNode(
        cluster_settings(
            node_id="node-0",
            port=p0,
            rate_limit_rps=0.01,
            rate_limit_burst=1,
        )
    )
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
        service0 = node0.cluster_service
        service1 = node1.cluster_service
        assert service0 is not None and service1 is not None

        async def joined() -> bool:
            return await service0.membership.get("node-1") is not None

        await wait_until(joined)
        client = DistributedClient(port=p0)
        assert await client.request("echo", {"id": 1}) == {"id": 1}
        with pytest.raises(RemoteTaskError) as exc:
            await client.request("echo", {"id": 2})
        assert exc.value.code == messages_pb2.RATE_LIMITED

        remote = await service0.membership.get("node-1")
        assert remote is not None
        ack = await service0.peer_client.ping(
            remote,
            await service0.membership.snapshot(),
            timeout_seconds=0.1,
        )
        assert ack.success is True
        assert ack.target_node_id == "node-1"
    finally:
        await node1.stop()
        await node0.stop()
