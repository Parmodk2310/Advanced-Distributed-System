import asyncio

import pytest

from distsys.client import DistributedClient, RemoteTaskError
from distsys.compute.router import TaskRouter
from distsys.node import DistributedNode
from distsys.proto import messages_pb2
from distsys.utils.config import Settings


async def slow_task(payload):
    await asyncio.sleep(0.1)
    return payload


@pytest.mark.asyncio
async def test_request_deadline_returns_timeout_error(unused_tcp_port):
    router = TaskRouter()
    router.register("slow", slow_task)
    node = DistributedNode(
        Settings(
            node_id="deadline-test",
            host="127.0.0.1",
            port=unused_tcp_port,
            request_timeout_seconds=0.02,
            rate_limit_rps=10_000.0,
            rate_limit_burst=100,
        ),
        router=router,
    )
    await node.start()
    try:
        client = DistributedClient(port=node.bound_port)
        with pytest.raises(RemoteTaskError) as exc:
            await client.request("slow", {"message": "late"})
        assert exc.value.code == messages_pb2.TIMEOUT
    finally:
        await node.stop()
