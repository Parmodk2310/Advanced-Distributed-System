from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from distsys.coordination.errors import CoordinationUnavailableError
from distsys.coordination.models import CoordinationMember, LeaseHandle
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


class ControlledCoordinationClient:
    def __init__(self) -> None:
        self.lease_counter = 0
        self.fail_next_refresh = True
        self.refresh_failed = asyncio.Event()
        self.allow_recovery = asyncio.Event()

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def grant_lease(self, ttl_seconds: int) -> LeaseHandle:
        if self.refresh_failed.is_set() and not self.allow_recovery.is_set():
            await self.allow_recovery.wait()
        self.lease_counter += 1
        return LeaseHandle(self.lease_counter, ttl_seconds)

    async def refresh_lease(self, lease: LeaseHandle) -> None:
        del lease
        if self.fail_next_refresh:
            self.fail_next_refresh = False
            self.refresh_failed.set()
            raise CoordinationUnavailableError("etcd unavailable")

    async def register_member(
        self,
        member: CoordinationMember,
        lease: LeaseHandle,
    ) -> None:
        del member, lease

    async def put_node_metadata(self, member: CoordinationMember) -> None:
        del member

    async def discover_members(self) -> tuple[CoordinationMember, ...]:
        return ()


@pytest.mark.asyncio
async def test_ready_node_marks_coordination_degraded_then_recovers(
    unused_tcp_port,
    tmp_path,
    monkeypatch,
):
    fake = ControlledCoordinationClient()
    monkeypatch.setattr(
        "distsys.node.EtcdGatewayCoordinationClient",
        lambda *args, **kwargs: fake,
    )
    settings = replace(
        cluster_settings(node_id="node-0", port=unused_tcp_port),
        crdt_enabled=True,
        crdt_replication_factor=1,
        persistence_enabled=True,
        persistence_db_path=str(tmp_path / "node-0.db"),
        etcd_enabled=True,
        etcd_endpoints=("http://127.0.0.1:2379",),
        etcd_lease_ttl_seconds=1,
        etcd_renew_interval_seconds=0.02,
    )
    node = DistributedNode(settings)
    await node.start()
    try:
        initial = await node.health.snapshot()
        assert initial.readiness is True
        assert initial.coordination is True

        await asyncio.wait_for(fake.refresh_failed.wait(), timeout=1.0)

        async def degraded() -> bool:
            snapshot = await node.health.snapshot()
            return snapshot.readiness and not snapshot.coordination

        await wait_until(degraded, timeout_seconds=0.5)

        fake.allow_recovery.set()

        async def recovered() -> bool:
            snapshot = await node.health.snapshot()
            return snapshot.readiness and snapshot.coordination

        await wait_until(recovered, timeout_seconds=1.0)
    finally:
        fake.allow_recovery.set()
        await node.stop()
