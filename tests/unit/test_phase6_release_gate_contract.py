from pathlib import Path


def test_release_gate_uses_direct_baseline_before_proxy_chaos() -> None:
    script = Path("scripts/phase6_release_gate.sh").read_text(encoding="utf-8")

    direct_start = script.index("start_cluster direct")
    observability = script.index("phase6_observability_smoke.py")
    monitoring = script.index("phase6_monitoring_smoke.py")
    task_benchmark = script.index("--workload task")
    crdt_benchmark = script.index("--workload crdt")
    baseline_stop = script.index("stop_cluster", crdt_benchmark)
    proxy_start = script.index("start_cluster proxy")
    chaos = script.index("for scenario in")

    assert (
        direct_start
        < observability
        < monitoring
        < task_benchmark
        < crdt_benchmark
        < baseline_stop
        < proxy_start
        < chaos
    )

    assert '--manifest "$CURRENT_LOG_DIR/manifest.json"' in script
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


def test_node_launcher_supports_direct_and_proxy_peer_routing() -> None:
    script = Path("scripts/phase6_start_node.sh").read_text(encoding="utf-8")

    assert 'PHASE6_PEER_ROUTING="${PHASE6_PEER_ROUTING:-direct}"' in script
    assert 'case "$PHASE6_PEER_ROUTING" in' in script
    assert "direct)" in script
    assert "proxy)" in script
    assert "unsupported PHASE6_PEER_ROUTING" in script

    assert "export RUN_CHAOS_TESTS=1 " "PHASE6_PEER_PROXY_MAP=" not in script


def test_phase6_observability_is_container_reachable_but_app_stays_loopback() -> None:
    script = Path("scripts/phase6_start_node.sh").read_text(encoding="utf-8")

    assert "NODE_HOST=127.0.0.1" in script
    assert 'OBSERVABILITY_HOST="${PHASE6_OBSERVABILITY_HOST:-0.0.0.0}"' in script
