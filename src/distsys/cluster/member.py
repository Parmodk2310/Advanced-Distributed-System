"""Cluster membership domain types."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum


class MemberStatus(IntEnum):
    ALIVE = 1
    SUSPECT = 2
    DEAD = 3


@dataclass(slots=True, frozen=True)
class ClusterMember:
    node_id: str
    host: str
    port: int
    status: MemberStatus
    incarnation: int

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id is required")
        if not self.host:
            raise ValueError("host is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.incarnation < 1:
            raise ValueError("incarnation must be positive")


@dataclass(slots=True, frozen=True)
class SeedAddress:
    host: str
    port: int
    node_id: str | None = None

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("seed host is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("seed port must be between 1 and 65535")

    @classmethod
    def parse(cls, raw: str) -> SeedAddress:
        value = raw.strip()
        if not value or ":" not in value:
            raise ValueError(f"invalid seed address: {raw!r}")
        endpoint = value
        node_id: str | None = None
        if "@" in value:
            raw_node_id, endpoint = value.split("@", 1)
            node_id = raw_node_id.strip()
            if not node_id:
                raise ValueError("seed node_id is required")
        host, raw_port = endpoint.rsplit(":", 1)
        host = host.strip()
        if not host:
            raise ValueError("seed host is required")
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ValueError(f"invalid seed port: {raw_port!r}") from exc
        return cls(host=host, port=port, node_id=node_id)


def fresh_incarnation() -> int:
    return time.time_ns()
