from __future__ import annotations

from distsys.coordination.models import CoordinationMember, LeaseHandle


class FakeCoordinationClient:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.members: tuple[CoordinationMember, ...] = ()
        self.lease_counter = 0
        self.fail_refresh = False

    async def connect(self) -> None:
        self.events.append("connect")

    async def close(self) -> None:
        self.events.append("close")

    async def grant_lease(self, ttl_seconds: int) -> LeaseHandle:
        self.lease_counter += 1
        self.events.append("grant")
        return LeaseHandle(self.lease_counter, ttl_seconds)

    async def refresh_lease(self, lease: LeaseHandle) -> None:
        self.events.append("refresh")
        if self.fail_refresh:
            self.fail_refresh = False
            raise RuntimeError("lost")

    async def register_member(self, member: CoordinationMember, lease: LeaseHandle) -> None:
        self.events.append("register")

    async def put_node_metadata(self, member: CoordinationMember) -> None:
        self.events.append("metadata")

    async def discover_members(self) -> tuple[CoordinationMember, ...]:
        self.events.append("discover")
        return self.members
