import pytest

from distsys.coordination.discovery import DiscoveryService
from distsys.coordination.lease import LeaseManager
from distsys.coordination.models import CoordinationMember
from distsys.coordination.service import CoordinationService
from tests.unit.coordination.fakes import FakeCoordinationClient


@pytest.mark.asyncio
async def test_coordination_bootstrap_order():
    client = FakeCoordinationClient()
    member = CoordinationMember("node-0", "u", "127.0.0.1", 18000, 1, 5, "0.5.0", True)
    manager = LeaseManager(client, ttl_seconds=15, renew_interval_seconds=5)
    service = CoordinationService(client, DiscoveryService(client), manager)
    await service.bootstrap(member)
    await service.stop()
    assert client.events[:5] == ["connect", "metadata", "discover", "grant", "register"]
