import pytest

from distsys.coordination.discovery import DiscoveryService
from distsys.coordination.models import CoordinationMember
from tests.unit.coordination.fakes import FakeCoordinationClient


def member(node_id: str, port: int) -> CoordinationMember:
    return CoordinationMember(node_id, f"u-{node_id}", "127.0.0.1", port, 1, 5, "0.5.0", True)


@pytest.mark.asyncio
async def test_discovery_filters_local_and_returns_identity_aware_seeds():
    client = FakeCoordinationClient()
    client.members = (member("node-2", 18002), member("node-0", 18000), member("node-1", 18001))
    seeds = await DiscoveryService(client).discover_seeds("node-0")
    assert [(s.node_id, s.port) for s in seeds] == [("node-1", 18001), ("node-2", 18002)]
