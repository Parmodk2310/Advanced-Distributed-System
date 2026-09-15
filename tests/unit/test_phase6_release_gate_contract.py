from pathlib import Path


def test_release_gate_benchmarks_clean_cluster_before_chaos() -> None:
    script = Path("scripts/phase6_release_gate.sh").read_text(encoding="utf-8")

    observability = script.index("phase6_observability_smoke.py")
    monitoring = script.index("phase6_monitoring_smoke.py")
    task_benchmark = script.index("--workload task")
    crdt_benchmark = script.index("--workload crdt")
    chaos = script.index("for scenario in")

    assert observability < monitoring < task_benchmark < crdt_benchmark < chaos
    assert "BREAKER_RECOVERY_WAIT_SECONDS" not in script


def test_cluster_runner_exits_after_signal_cleanup() -> None:
    script = Path("scripts/run_phase6_cluster.sh").read_text(encoding="utf-8")

    assert "trap cleanup EXIT" in script
    assert "trap terminate INT TERM" in script
    terminate = script[script.index("terminate() {") :]
    terminate = terminate[: terminate.index("}\n")]

    assert "cleanup" in terminate
    assert "exit 0" in terminate
    assert "while true; do sleep 3600; done" not in script
    assert "RUNNER_IDLE_PID=$!" in script
    assert 'wait "$RUNNER_IDLE_PID"' in script
