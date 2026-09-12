import asyncio
import time

import pytest

from distsys.client import DistributedClient
from distsys.node import DistributedNode
from distsys.utils.config import Settings


@pytest.mark.asyncio
async def test_cpu_work_does_not_block_echo_requests(unused_tcp_port):
    node = DistributedNode(
        Settings(
            node_id="responsive-test",
            host="127.0.0.1",
            port=unused_tcp_port,
            cpu_workers=2,
            rate_limit_rps=10_000.0,
            rate_limit_burst=1_000,
            request_timeout_seconds=5.0,
        )
    )
    await node.start()
    try:
        cpu_client = DistributedClient(port=node.bound_port)
        echo_client = DistributedClient(port=node.bound_port)
        cpu_request = asyncio.create_task(
            cpu_client.request("hash", {"data": "responsiveness", "rounds": 300_000})
        )
        await asyncio.sleep(0.01)

        started = time.perf_counter()
        assert await echo_client.request("echo", {"message": "still-responsive"}) == {
            "message": "still-responsive"
        }
        elapsed = time.perf_counter() - started

        assert elapsed < 0.5
        await cpu_request
    finally:
        await node.stop()
