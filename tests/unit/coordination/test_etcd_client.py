from __future__ import annotations

import threading

import pytest

from distsys.coordination.etcd_client import EtcdGatewayCoordinationClient
from distsys.coordination.models import CoordinationMember


class FakeLease:
    def __init__(self, lease_id: int, events: list[tuple[str, int]]):
        self.id = lease_id
        self.events = events

    def refresh(self):
        self.events.append(("refresh", threading.get_ident()))
        return 15


class FakeClient:
    def __init__(self, *, ok: bool = True):
        self.ok = ok
        self.events: list[tuple[str, int]] = []
        self.values: dict[str, bytes] = {}

    def status(self):
        self.events.append(("status", threading.get_ident()))
        if not self.ok:
            raise OSError("unavailable")
        return {"version": "3.6"}

    def lease(self, ttl=30):
        self.events.append(("lease", threading.get_ident()))
        return FakeLease(42, self.events)

    def put(self, key, value, lease=None):
        self.events.append(("put", threading.get_ident()))
        self.values[str(key)] = value.encode() if isinstance(value, str) else value
        return True

    def get_prefix(self, prefix):
        self.events.append(("get_prefix", threading.get_ident()))
        return [
            (value, {"key": key.encode()})
            for key, value in self.values.items()
            if key.startswith(prefix)
        ]


@pytest.mark.asyncio
async def test_adapter_runs_blocking_etcd_calls_off_event_loop_thread():
    loop_thread = threading.get_ident()
    fake = FakeClient()
    client = EtcdGatewayCoordinationClient(
        ("http://127.0.0.1:2379",),
        namespace="/distsys/v1",
        client_factory=lambda **kwargs: fake,
    )
    await client.connect()
    lease = await client.grant_lease(15)
    member = CoordinationMember("node-0", "u", "127.0.0.1", 18000, 1, 5, "0.5.0", False)
    await client.register_member(member, lease)
    await client.refresh_lease(lease)
    await client.discover_members()
    assert fake.events
    assert all(thread_id != loop_thread for _, thread_id in fake.events)


@pytest.mark.asyncio
async def test_adapter_fails_over_to_second_endpoint():
    first = FakeClient(ok=False)
    second = FakeClient(ok=True)
    created = iter([first, second])
    client = EtcdGatewayCoordinationClient(
        ("http://one:2379", "http://two:2379"),
        namespace="/distsys/v1",
        client_factory=lambda **kwargs: next(created),
    )
    await client.connect()
    assert client.active_endpoint == "http://two:2379"


@pytest.mark.asyncio
async def test_expired_etcd_lease_refresh_is_reported_unavailable():
    class ExpiredLease(FakeLease):
        def refresh(self):
            self.events.append(("refresh", threading.get_ident()))
            return -1

    class ExpiredLeaseClient(FakeClient):
        def lease(self, ttl=30):
            self.events.append(("lease", threading.get_ident()))
            return ExpiredLease(43, self.events)

    fake = ExpiredLeaseClient()
    client = EtcdGatewayCoordinationClient(
        ("http://127.0.0.1:2379",),
        namespace="/distsys/v1",
        client_factory=lambda **kwargs: fake,
    )
    await client.connect()
    lease = await client.grant_lease(15)

    from distsys.coordination.errors import CoordinationUnavailableError

    with pytest.raises(CoordinationUnavailableError, match="expired"):
        await client.refresh_lease(lease)
