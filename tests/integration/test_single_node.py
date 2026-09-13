import asyncio

import pytest

from distsys.client import DistributedClient, RemoteTaskError
from distsys.cluster.codec import encode_ping
from distsys.node import DistributedNode
from distsys.proto import messages_pb2
from distsys.protocol.codec import decode_task_response
from distsys.protocol.framing import encode_frame, read_message
from distsys.protocol.message import Message, MessageType
from distsys.utils.config import Settings


async def _wait_until_listening(node: DistributedNode, timeout_seconds: float = 2.0) -> None:
    """Wait for WSL localhost forwarding to expose a newly bound port."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        try:
            reader, writer = await asyncio.open_connection(
                node.settings.host,
                node.bound_port,
            )
        except ConnectionRefusedError:
            if loop.time() >= deadline:
                raise
            await asyncio.sleep(0.02)
            continue

        del reader
        writer.close()
        await writer.wait_closed()
        return


@pytest.fixture
async def running_node():
    node = DistributedNode(Settings(node_id="node-test", host="127.0.0.1", port=0))
    await node.start()
    await _wait_until_listening(node)
    try:
        yield node
    finally:
        await node.stop()


@pytest.mark.asyncio
async def test_running_node_uses_kernel_assigned_port(running_node):
    assert running_node.settings.port == 0
    assert running_node.bound_port > 0


@pytest.mark.asyncio
async def test_echo_round_trip(running_node):
    client = DistributedClient(port=running_node.bound_port)
    payload = {"message": "hello", "value": 42}
    assert await client.request("echo", payload) == payload


@pytest.mark.asyncio
async def test_unknown_task_returns_structured_error(running_node):
    client = DistributedClient(port=running_node.bound_port)
    with pytest.raises(RemoteTaskError) as exc:
        await client.request("does-not-exist", {})
    assert exc.value.code == messages_pb2.UNKNOWN_TASK


@pytest.mark.asyncio
async def test_multiple_clients(running_node):
    # Keep the test concurrent while avoiding a 50-SYN burst through WSL's
    # localhost forwarding layer. A transient refusal is retried only while
    # the in-process server still reports itself as serving.
    concurrency = asyncio.Semaphore(8)

    async def one(index: int):
        async with concurrency:
            client = DistributedClient(
                port=running_node.bound_port,
                client_id=f"client-{index}",
            )
            payload = {"index": index}
            for attempt in range(5):
                try:
                    return await client.request("echo", payload)
                except ConnectionRefusedError:
                    assert running_node.is_running
                    if attempt == 4:
                        raise
                    await asyncio.sleep(0.02)
        raise AssertionError("unreachable")

    results = await asyncio.gather(*(one(index) for index in range(50)))
    assert results == [{"index": index} for index in range(50)]


@pytest.mark.asyncio
async def test_clean_stop(running_node):
    port = running_node.bound_port
    await running_node.stop()
    assert not running_node.is_running

    # Rebinding proves the Linux listener was released without depending on
    # WSL/Windows localhost-forwarding teardown timing.
    rebound = await asyncio.start_server(lambda _r, w: w.close(), "127.0.0.1", port)
    rebound.close()
    await rebound.wait_closed()


@pytest.mark.asyncio
async def test_persistent_connection_multiple_requests(running_node):
    client = DistributedClient(port=running_node.bound_port)
    await client.connect()
    try:
        for index in range(100):
            payload = {"index": index, "message": "persistent"}
            assert await client.request_connected("echo", payload) == payload
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_routing_key_is_ignored_when_cluster_mode_is_disabled():
    node = DistributedNode(Settings(node_id="standalone", host="127.0.0.1", port=0))
    await node.start()
    await _wait_until_listening(node)
    try:
        client = DistributedClient(port=node.bound_port)
        result = await client.request(
            "echo",
            {"message": "local"},
            routing_key="customer-123",
        )
        assert result == {"message": "local"}
    finally:
        await node.stop()


@pytest.mark.asyncio
async def test_cluster_control_is_rejected_when_cluster_mode_is_disabled():
    node = DistributedNode(Settings(node_id="standalone", host="127.0.0.1", port=0))
    await node.start()
    await _wait_until_listening(node)
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", node.bound_port)
        request = Message.new_request(
            sender_id="node-1",
            msg_type=MessageType.PING,
            payload=encode_ping(()),
        )
        writer.write(encode_frame(request))
        await writer.drain()
        response = await read_message(reader)
        decoded = decode_task_response(response.payload)

        assert response.msg_type is MessageType.ERROR
        assert decoded.error_code == messages_pb2.INVALID_REQUEST

        writer.close()
        await writer.wait_closed()
    finally:
        await node.stop()


@pytest.mark.asyncio
async def test_cluster_whoami_reports_local_node_identity():
    node = DistributedNode(Settings(node_id="standalone", host="127.0.0.1", port=0))
    await node.start()
    await _wait_until_listening(node)
    try:
        client = DistributedClient(port=node.bound_port)
        assert await client.request("cluster.whoami", {}) == {"node_id": "standalone"}
    finally:
        await node.stop()
