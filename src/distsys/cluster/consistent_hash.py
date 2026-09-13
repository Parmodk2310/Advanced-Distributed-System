"""Deterministic SHA-256 consistent hash ring."""

from __future__ import annotations

import bisect
import hashlib
from collections.abc import Iterable

from distsys.cluster.member import ClusterMember, MemberStatus


class NoRouteError(LookupError):
    """Raised when no ALIVE cluster member can own a routing key."""


def _hash(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest(), "big")


class ConsistentHashRing:
    def __init__(self, *, virtual_nodes: int = 64) -> None:
        if virtual_nodes < 1:
            raise ValueError("virtual_nodes must be at least 1")
        self.virtual_nodes = virtual_nodes
        self._positions: list[int] = []
        self._owners: list[ClusterMember] = []

    def rebuild(self, members: Iterable[ClusterMember]) -> None:
        points: list[tuple[int, ClusterMember]] = []
        for member in members:
            if member.status is not MemberStatus.ALIVE:
                continue
            for index in range(self.virtual_nodes):
                points.append((_hash(f"{member.node_id}#{index}"), member))
        points.sort(key=lambda item: (item[0], item[1].node_id))
        self._positions = [position for position, _ in points]
        self._owners = [member for _, member in points]

    def candidates(self, key: str) -> list[ClusterMember]:
        if not self._positions:
            raise NoRouteError("no ALIVE cluster members are available")
        start = bisect.bisect_left(self._positions, _hash(key))
        result: list[ClusterMember] = []
        seen: set[str] = set()
        for offset in range(len(self._owners)):
            member = self._owners[(start + offset) % len(self._owners)]
            if member.node_id in seen:
                continue
            seen.add(member.node_id)
            result.append(member)
        return result

    def owner(self, key: str) -> ClusterMember:
        return self.candidates(key)[0]
