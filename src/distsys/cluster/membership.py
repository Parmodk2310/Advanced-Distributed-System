"""Atomic cluster membership state and SWIM-style merge rules."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import replace

from distsys.cluster.member import ClusterMember, MemberStatus

logger = logging.getLogger("distsys.cluster.membership")


class MembershipTable:
    def __init__(
        self,
        local_member: ClusterMember,
        *,
        suspicion_timeout_seconds: float,
        dead_retention_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if suspicion_timeout_seconds <= 0:
            raise ValueError("suspicion timeout must be greater than zero")
        if dead_retention_seconds <= suspicion_timeout_seconds:
            raise ValueError("dead retention must exceed suspicion timeout")
        self.local_node_id = local_member.node_id
        self.suspicion_timeout_seconds = suspicion_timeout_seconds
        self.dead_retention_seconds = dead_retention_seconds
        self._clock = clock
        self._members: dict[str, ClusterMember] = {local_member.node_id: local_member}
        self._suspected_at: dict[str, float] = {}
        self._dead_at: dict[str, float] = {}
        self._version = 1
        self._lock = asyncio.Lock()

    @property
    def version(self) -> int:
        return self._version

    async def snapshot(self) -> tuple[ClusterMember, ...]:
        async with self._lock:
            return tuple(self._members[key] for key in sorted(self._members))

    async def get(self, node_id: str) -> ClusterMember | None:
        async with self._lock:
            return self._members.get(node_id)

    async def alive_members(self, *, include_self: bool = True) -> tuple[ClusterMember, ...]:
        async with self._lock:
            return tuple(
                member
                for node_id, member in sorted(self._members.items())
                if member.status is MemberStatus.ALIVE
                and (include_self or node_id != self.local_node_id)
            )

    async def probe_candidates(self) -> tuple[ClusterMember, ...]:
        async with self._lock:
            return tuple(
                member
                for node_id, member in sorted(self._members.items())
                if node_id != self.local_node_id
                and member.status in (MemberStatus.ALIVE, MemberStatus.SUSPECT)
            )

    def _record_timer_state(self, member: ClusterMember) -> None:
        now = self._clock()
        if member.status is MemberStatus.ALIVE:
            self._suspected_at.pop(member.node_id, None)
            self._dead_at.pop(member.node_id, None)
        elif member.status is MemberStatus.SUSPECT:
            self._suspected_at.setdefault(member.node_id, now)
            self._dead_at.pop(member.node_id, None)
        else:
            self._suspected_at.pop(member.node_id, None)
            self._dead_at.setdefault(member.node_id, now)

    def _merge_one_locked(self, incoming: ClusterMember) -> bool:
        current = self._members.get(incoming.node_id)

        if incoming.node_id == self.local_node_id:
            assert current is not None
            if (
                incoming.status in (MemberStatus.SUSPECT, MemberStatus.DEAD)
                and incoming.incarnation >= current.incarnation
            ):
                refuted = replace(
                    current,
                    status=MemberStatus.ALIVE,
                    incarnation=incoming.incarnation + 1,
                )
                self._members[self.local_node_id] = refuted
                self._record_timer_state(refuted)
                logger.info(
                    "local member refuted suspicion",
                    extra={
                        "event": "member_refuted",
                        "node_id": self.local_node_id,
                        "incarnation": refuted.incarnation,
                    },
                )
                return True
            return False

        if current is None:
            self._members[incoming.node_id] = incoming
            self._record_timer_state(incoming)
            return True

        if incoming.incarnation < current.incarnation:
            return False

        if incoming.incarnation > current.incarnation:
            self._members[incoming.node_id] = incoming
            self._record_timer_state(incoming)
            return True

        if incoming.status > current.status:
            updated = replace(current, status=incoming.status)
            self._members[incoming.node_id] = updated
            self._record_timer_state(updated)
            return True

        return False

    async def merge(self, records: Iterable[ClusterMember]) -> bool:
        async with self._lock:
            changed = False
            for record in records:
                changed = self._merge_one_locked(record) or changed
            if changed:
                self._version += 1
            return changed

    async def mark_suspect(self, node_id: str) -> bool:
        async with self._lock:
            current = self._members.get(node_id)
            if current is None or node_id == self.local_node_id:
                return False
            if current.status is not MemberStatus.ALIVE:
                return False
            updated = replace(current, status=MemberStatus.SUSPECT)
            self._members[node_id] = updated
            self._record_timer_state(updated)
            self._version += 1
            logger.info(
                "member suspected",
                extra={"event": "member_suspect", "node_id": node_id},
            )
            return True

    async def advance_timeouts_and_purge(self) -> bool:
        async with self._lock:
            now = self._clock()
            changed = False

            for node_id, suspected_at in list(self._suspected_at.items()):
                member = self._members.get(node_id)
                if member is None or member.status is not MemberStatus.SUSPECT:
                    self._suspected_at.pop(node_id, None)
                    continue
                if now - suspected_at >= self.suspicion_timeout_seconds:
                    updated = replace(member, status=MemberStatus.DEAD)
                    self._members[node_id] = updated
                    self._suspected_at.pop(node_id, None)
                    self._dead_at[node_id] = now
                    logger.info(
                        "member declared dead",
                        extra={"event": "member_dead", "node_id": node_id},
                    )
                    changed = True

            for node_id, dead_at in list(self._dead_at.items()):
                if node_id == self.local_node_id:
                    continue
                member = self._members.get(node_id)
                if member is None or member.status is not MemberStatus.DEAD:
                    self._dead_at.pop(node_id, None)
                    continue
                if now - dead_at >= self.dead_retention_seconds:
                    self._members.pop(node_id, None)
                    self._dead_at.pop(node_id, None)
                    changed = True

            if changed:
                self._version += 1
            return changed
