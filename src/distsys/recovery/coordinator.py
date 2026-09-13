"""High-level recovery state transitions for durable node startup."""

from __future__ import annotations

from typing import Any, Protocol

from distsys.health import HealthState, RecoveryPhase


class RestoreServiceLike(Protocol):
    async def restore(self) -> Any: ...


class ReconcilerLike(Protocol):
    async def reconcile(self, peers: tuple[Any, ...]) -> Any: ...


class RecoveryCoordinator:
    def __init__(
        self,
        *,
        health: HealthState,
        restore_service: RestoreServiceLike,
        reconciler: ReconcilerLike | None = None,
    ) -> None:
        self.health = health
        self.restore_service = restore_service
        self.reconciler = reconciler

    async def prepare_persistence(self) -> Any:
        await self.health.set_recovery_phase(RecoveryPhase.OPENING_REPOSITORY)
        await self.health.set_recovery_phase(RecoveryPhase.RESTORING)
        return await self.restore_service.restore()

    async def mark_binding(self) -> None:
        await self.health.set_recovery_phase(RecoveryPhase.BINDING)

    async def mark_coordinating(self) -> None:
        await self.health.set_recovery_phase(RecoveryPhase.COORDINATING)

    async def mark_joining_cluster(self) -> None:
        await self.health.set_recovery_phase(RecoveryPhase.JOINING_CLUSTER)

    async def reconcile(self, peers: tuple[Any, ...]) -> Any:
        await self.health.set_recovery_phase(RecoveryPhase.RECONCILING)
        result = None
        if self.reconciler is not None:
            result = await self.reconciler.reconcile(peers)
        await self.health.set_readiness(True)
        await self.health.set_recovery_phase(RecoveryPhase.READY)
        return result

    async def fail(self, exc: BaseException) -> None:
        await self.health.set_readiness(False)
        await self.health.set_recovery_phase(RecoveryPhase.STARTUP_FAILED, str(exc))
