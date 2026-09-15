from distsys.benchmarking.aggregate import aggregate_runs
from distsys.benchmarking.model import (
    BenchmarkConfig,
    BenchmarkResult,
    CorrectnessCheck,
    LatencySummary,
)


def _result(seed: int, throughput: float, p95: float, *, valid: bool = True) -> BenchmarkResult:
    return BenchmarkResult(
        timestamp_utc=f"2026-09-14T00:00:0{seed}Z",
        git_commit="abc",
        git_dirty=False,
        environment={"logical_cores": 8},
        config=BenchmarkConfig(profile="formal", workload="task", seed=seed),
        successes=100 if valid else 99,
        failures={} if valid else {"correctness": 1},
        throughput_rps=throughput,
        latency=LatencySummary(0.01, p95, p95 + 0.01, p95 + 0.02),
        correctness=(CorrectnessCheck("workload_semantics", valid),),
    )


def test_aggregate_runs_requires_five_formal_runs_and_reports_medians() -> None:
    runs = tuple(
        _result(seed, throughput, p95)
        for seed, throughput, p95 in [
            (1, 100.0, 0.10),
            (2, 90.0, 0.12),
            (3, 110.0, 0.08),
            (4, 95.0, 0.11),
            (5, 105.0, 0.09),
        ]
    )

    summary = aggregate_runs(runs)

    assert summary.run_count == 5
    assert summary.valid_runs == 5
    assert summary.median_throughput_rps == 100.0
    assert summary.median_p95_seconds == 0.10
    assert summary.throughput_min_rps == 90.0
    assert summary.throughput_max_rps == 110.0
    assert summary.all_valid is True


def test_aggregate_runs_rejects_fewer_than_five_formal_runs() -> None:
    runs = tuple(_result(seed, 100.0, 0.1) for seed in range(1, 5))
    try:
        aggregate_runs(runs)
    except ValueError as exc:
        assert "at least five" in str(exc)
    else:
        raise AssertionError("expected formal aggregate validation failure")
