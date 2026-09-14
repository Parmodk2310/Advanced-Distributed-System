"""Machine-readable chaos probe and scenario results."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class ProbeState:
    ready_nodes: tuple[str, ...]
    coordination_healthy_nodes: tuple[str, ...]
    target_reachable: bool
    peer_latency_seconds: float | None
    data_plane_ok: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario: str
    started_utc: str
    ended_utc: str
    expected_effect: str
    observed_effect: str
    recovery_seconds: float
    cleanup_ok: bool
    passed: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
