import asyncio
import socket

import pytest

from distsys.observed_node import ObservedDistributedNode
from distsys.utils.config import Settings


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_real_node_exposes_independent_metrics_and_health_listener():
    app_port, obs_port = free_port(), free_port()
    node = ObservedDistributedNode(
        Settings(
            port=app_port,
            etcd_enabled=False,
            persistence_enabled=False,
            observability_enabled=True,
            observability_port=obs_port,
            tracing_enabled=False,
        )
    )
    await node.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", obs_port)
        writer.write(
            b"GET /health/ready HTTP/1.1\r\n" b"Host: localhost\r\n" b"Connection: close\r\n\r\n"
        )
        await writer.drain()
        body = await reader.read()
        writer.close()
        await writer.wait_closed()
        assert b"200 OK" in body
        assert b'"readiness":true' in body
    finally:
        await node.stop()
