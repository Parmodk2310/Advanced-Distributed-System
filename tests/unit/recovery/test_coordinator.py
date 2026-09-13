from __future__ import annotations

import pytest

from distsys.health import HealthState, RecoveryPhase
from distsys.recovery.coordinator import RecoveryCoordinator


class Restore:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def restore(self):
        self.calls += 1
        return self.result


class Reconciler:
    def __init__(self):
        self.calls = []

    async def reconcile(self, peers):
        self.calls.append(tuple(peers))
        return {"ok": True}


@pytest.mark.asyncio
async def test_prepare_persistence_sets_restore_phase_and_returns_state():
    health = HealthState()
    restore = Restore(object())
    coordinator = RecoveryCoordinator(health=health, restore_service=restore)
    result = await coordinator.prepare_persistence()
    assert result is restore.result
    assert restore.calls == 1
    assert (await health.snapshot()).recovery_phase is RecoveryPhase.RESTORING


@pytest.mark.asyncio
async def test_reconcile_marks_ready_after_success():
    health = HealthState()
    reconciler = Reconciler()
    coordinator = RecoveryCoordinator(
        health=health,
        restore_service=Restore(object()),
        reconciler=reconciler,
    )
    result = await coordinator.reconcile(("peer-a", "peer-b"))
    snapshot = await health.snapshot()
    assert result == {"ok": True}
    assert snapshot.recovery_phase is RecoveryPhase.READY
    assert snapshot.readiness is True


@pytest.mark.asyncio
async def test_fail_marks_startup_failed_and_not_ready():
    health = HealthState()
    coordinator = RecoveryCoordinator(health=health, restore_service=Restore(object()))
    await coordinator.fail(RuntimeError("boom"))
    snapshot = await health.snapshot()
    assert snapshot.recovery_phase is RecoveryPhase.STARTUP_FAILED
    assert snapshot.readiness is False
    assert snapshot.last_error == "boom"
