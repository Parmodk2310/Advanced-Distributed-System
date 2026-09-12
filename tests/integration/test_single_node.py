import asyncio

import pytest

from distsys.client import DistributedClient, RemoteTaskError
from distsys.node import DistributedNode
from distsys.proto import messages_pb2
from distsys.utils.config import Settings


@pytest.fixture
async def running_node(unused_tcp_port):
    node = DistributedNode(
        Settings(node_id="node-test", host="127.0.0.1", port=unused_tcp_port)
    )
    await node.start()

    try:
        yield node
    finally:
        await node.stop()


def client_for(node, *, client_id="client"):
    return DistributedClient(
        host="127.0.0.1",
        port=node.bound_port,
        client_id=client_id,
    )


@pytest.mark.asyncio
async def test_echo_round_trip(running_node):
    payload = {"message": "hello", "value": 42}
    assert await client_for(running_node).request("echo", payload) == payload


@pytest.mark.asyncio
async def test_unknown_task_returns_structured_error(running_node):
    with pytest.raises(RemoteTaskError) as exc:
        await client_for(running_node).request("does-not-exist", {})

    assert exc.value.code == messages_pb2.UNKNOWN_TASK


@pytest.mark.asyncio
async def test_multiple_clients(running_node):
    async def request(index):
        payload = {"index": index}
        client = client_for(running_node, client_id=f"client-{index}")
        return await client.request("echo", payload)

    results = await asyncio.gather(*(request(i) for i in range(10)))
    assert results == [{"index": i} for i in range(10)]


@pytest.mark.asyncio
async def test_clean_stop(running_node):
    assert running_node.is_running
    await running_node.stop()
    assert not running_node.is_running


@pytest.mark.asyncio
async def test_persistent_connection_multiple_requests(running_node):
    client = client_for(running_node)
    await client.connect()

    try:
        for index in range(100):
            payload = {"index": index, "message": "persistent"}
            assert await client.request_connected("echo", payload) == payload
    finally:
        await client.close()