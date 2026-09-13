"""Concurrency-safe node health and recovery state."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from enum import Enum


class RecoveryPhase(str, Enum):
    STARTING = "starting"
    OPENING_REPOSITORY = "opening_repository"
    RESTORING = "restoring"
    BINDING = "binding"
    COORDINATING = "coordinating"
    JOINING_CLUSTER = "joining_cluster"
    RECONCILING = "reconciling"
    READY = "ready"
    STARTUP_FAILED = "startup_failed"


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    liveness: bool = True
    readiness: bool = False
    coordination: bool = False
    cluster: bool = False
    recovery_phase: RecoveryPhase = RecoveryPhase.STARTING
    coordination_message: str = ""
    last_error: str = ""


class HealthState:
    def __init__(self) -> None:
        self._snapshot = HealthSnapshot()
        self._lock = asyncio.Lock()

    async def snapshot(self) -> HealthSnapshot:
        async with self._lock:
            return self._snapshot

    async def set_recovery_phase(self, phase: RecoveryPhase, error: str = "") -> None:
        async with self._lock:
            self._snapshot = replace(self._snapshot, recovery_phase=phase, last_error=error)

    async def set_readiness(self, ready: bool) -> None:
        async with self._lock:
            self._snapshot = replace(self._snapshot, readiness=ready)

    async def set_coordination(self, healthy: bool, message: str = "") -> None:
        async with self._lock:
            self._snapshot = replace(
                self._snapshot,
                coordination=healthy,
                coordination_message=message,
            )

    async def set_cluster(self, healthy: bool) -> None:
        async with self._lock:
            self._snapshot = replace(self._snapshot, cluster=healthy)

    async def set_liveness(self, healthy: bool) -> None:
        async with self._lock:
            self._snapshot = replace(self._snapshot, liveness=healthy)
