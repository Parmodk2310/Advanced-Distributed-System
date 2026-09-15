from pathlib import Path


def test_release_gate_waits_for_circuit_breaker_recovery_before_benchmarks() -> None:
    script = Path("scripts/phase6_release_gate.sh").read_text(encoding="utf-8")

    chaos_end = script.index('done\n', script.index("for scenario in"))
    recovery_wait = script.index('sleep "$BREAKER_RECOVERY_WAIT_SECONDS"', chaos_end)
    task_benchmark = script.index("--workload task", recovery_wait)
    expected_wait_setting = (
        'BREAKER_RECOVERY_WAIT_SECONDS="${PHASE6_BREAKER_RECOVERY_WAIT_SECONDS:-11}"'
    )

    assert expected_wait_setting in script
    assert chaos_end < recovery_wait < task_benchmark
