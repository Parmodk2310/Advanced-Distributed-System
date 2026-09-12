import asyncio

import pytest

from distsys.client import DistributedClient, RemoteTaskError
from distsys.compute.router import TaskRouter
from distsys.compute.tasks import echo_task
from distsys.node import DistributedNode
from distsys.proto import messages_pb2
from distsys.utils.config import Settings


async def slow_task(payload):
    await asyncio.sleep(0.15)
    return payload


@pytest.mark.asyncio
async def test_backpressure_returns_overloaded_error(unused_tcp_port):
    router = TaskRouter()
    router.register("echo", echo_task)
    router.register("slow", slow_task)
    node = DistributedNode(
        Settings(
            node_id="overload-test",
            host="127.0.0.1",
            port=unused_tcp_port,
            cpu_queue_capacity=1,
            rate_limit_rps=10_000.0,
            rate_limit_burst=1_000,
        ),
        router=router,
    )
    await node.start()
    try:
        client_one = DistributedClient(port=node.bound_port)
        client_two = DistributedClient(port=node.bound_port)
        first = asyncio.create_task(client_one.request("slow", {"id": 1}))
        await asyncio.sleep(0.03)

        with pytest.raises(RemoteTaskError) as exc:
            await client_two.request("echo", {"id": 2})
        assert exc.value.code == messages_pb2.OVERLOADED
        assert await first == {"id": 1}
    finally:
        await node.stop()


@pytest.mark.asyncio
async def test_rate_limiter_returns_structured_error(unused_tcp_port):
    node = DistributedNode(
        Settings(
            node_id="rate-test",
            host="127.0.0.1",
            port=unused_tcp_port,
            rate_limit_rps=0.01,
            rate_limit_burst=1,
        )
    )
    await node.start()
    try:
        client = DistributedClient(port=node.bound_port)
        assert await client.request("echo", {"id": 1}) == {"id": 1}
        with pytest.raises(RemoteTaskError) as exc:
            await client.request("echo", {"id": 2})
        assert exc.value.code == messages_pb2.RATE_LIMITED
    finally:
        await node.stop()
