import pytest

from distsys.health.state import HealthState, RecoveryPhase


@pytest.mark.asyncio
async def test_health_allows_ready_with_coordination_degraded():
    health = HealthState()
    await health.set_recovery_phase(RecoveryPhase.READY)
    await health.set_readiness(True)
    await health.set_coordination(False, "etcd down")
    snap = await health.snapshot()
    assert snap.readiness is True
    assert snap.coordination is False
    assert snap.recovery_phase is RecoveryPhase.READY
