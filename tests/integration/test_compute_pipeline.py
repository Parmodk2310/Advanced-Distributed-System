import hashlib

import pytest

from distsys.client import DistributedClient
from distsys.node import DistributedNode
from distsys.utils.config import Settings


@pytest.fixture
async def compute_node(unused_tcp_port):
    node = DistributedNode(
        Settings(
            node_id="compute-test",
            host="127.0.0.1",
            port=unused_tcp_port,
            rate_limit_rps=10_000.0,
            rate_limit_burst=1_000,
        )
    )
    await node.start()
    try:
        yield node
    finally:
        await node.stop()


@pytest.mark.asyncio
async def test_cpu_compute_tasks_round_trip(compute_node):
    client = DistributedClient(port=compute_node.bound_port)

    hashed = await client.request("hash", {"data": "hello", "rounds": 1})
    assert hashed == {
        "algorithm": "sha256",
        "digest": hashlib.sha256(b"hello").hexdigest(),
        "rounds": 1,
    }

    sorted_result = await client.request("sort", {"values": [5, 1, 3]})
    assert sorted_result == {"values": [1, 3, 5], "count": 3}

    aggregate = await client.request("aggregate", {"values": [1, 2, 3, 4]})
    assert aggregate == {
        "count": 4,
        "sum": 10.0,
        "min": 1.0,
        "max": 4.0,
        "mean": 2.5,
    }
