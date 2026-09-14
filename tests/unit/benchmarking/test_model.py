import json

from distsys.benchmarking.model import (
    BenchmarkConfig,
    BenchmarkResult,
    CorrectnessCheck,
    LatencySummary,
)


def test_result_json_is_deterministic_and_validity_includes_correctness():
    config = BenchmarkConfig(
        profile="quick",
        workload="task",
        concurrency=4,
        warmup_seconds=0.1,
        duration_seconds=0.2,
        payload_size=16,
        read_ratio=0.8,
        seed=7,
    )
    result = BenchmarkResult(
        timestamp_utc="2026-09-14T00:00:00Z",
        git_commit="abc",
        git_dirty=False,
        environment={"python": "3.12"},
        config=config,
        successes=99,
        failures={},
        throughput_rps=10.0,
        latency=LatencySummary(0.01, 0.02, 0.03, 0.04),
        correctness=(CorrectnessCheck("echo", True, "ok"),),
    )
    a = result.to_json()
    b = result.to_json()
    assert a == b
    assert json.loads(a)["valid"] is True
