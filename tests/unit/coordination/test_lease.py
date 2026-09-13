import asyncio

import pytest

from distsys.coordination.lease import LeaseManager
from distsys.coordination.models import CoordinationMember
from tests.unit.coordination.fakes import FakeCoordinationClient


def member() -> CoordinationMember:
    return CoordinationMember("node-0", "u", "127.0.0.1", 18000, 1, 5, "0.5.0", True)


@pytest.mark.asyncio
async def test_lease_manager_acquires_registers_and_refreshes():
    client = FakeCoordinationClient()
    manager = LeaseManager(client, ttl_seconds=15, renew_interval_seconds=0.01)
    await manager.start(member())
    await asyncio.sleep(0.03)
    await manager.stop()
    assert client.events[:2] == ["grant", "register"]
    assert "refresh" in client.events


@pytest.mark.asyncio
async def test_lease_manager_reacquires_after_refresh_failure():
    client = FakeCoordinationClient()
    client.fail_refresh = True
    manager = LeaseManager(client, ttl_seconds=15, renew_interval_seconds=0.01)
    await manager.start(member())
    await asyncio.sleep(0.05)
    assert client.events.count("grant") >= 2
    assert client.events.count("register") >= 2
    assert manager.health.healthy is True
    await manager.stop()


@pytest.mark.asyncio
async def test_lease_manager_reports_degraded_then_recovered_health():
    client = FakeCoordinationClient()
    client.fail_refresh = True
    seen = []

    async def on_health_change(health):
        seen.append(health)

    manager = LeaseManager(
        client,
        ttl_seconds=15,
        renew_interval_seconds=0.01,
        on_health_change=on_health_change,
    )
    await manager.start(member())
    await asyncio.sleep(0.05)
    await manager.stop()

    assert any(not item.healthy for item in seen)
    assert any(item.healthy for item in seen)
