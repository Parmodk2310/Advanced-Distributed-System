"""Formal multi-run benchmark aggregation for Phase 6 evidence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from statistics import median

from distsys.benchmarking.model import BenchmarkResult


@dataclass(frozen=True, slots=True)
class BenchmarkAggregate:
    """Median and variability summary across independent formal benchmark runs."""

    run_count: int
    valid_runs: int
    median_throughput_rps: float
    median_p95_seconds: float
    throughput_min_rps: float
    throughput_max_rps: float
    p95_min_seconds: float
    p95_max_seconds: float
    all_valid: bool
    git_commit: str
    git_dirty_runs: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def _comparable_signature(result: BenchmarkResult) -> tuple[object, ...]:
    config = result.config
    return (
        config.profile,
        config.workload,
        config.concurrency,
        config.warmup_seconds,
        config.duration_seconds,
        config.payload_size,
        config.read_ratio,
    )


def aggregate_runs(runs: tuple[BenchmarkResult, ...]) -> BenchmarkAggregate:
    """Aggregate at least five comparable formal runs without hiding invalid runs."""

    if len(runs) < 5:
        raise ValueError("formal benchmark aggregation requires at least five runs")
    if any(result.config.profile != "formal" for result in runs):
        raise ValueError("all aggregated runs must use the formal profile")

    signature = _comparable_signature(runs[0])
    if any(_comparable_signature(result) != signature for result in runs[1:]):
        raise ValueError("formal benchmark runs must use comparable workload settings")

    commits = {result.git_commit for result in runs}
    if len(commits) != 1:
        raise ValueError("formal benchmark runs must come from one git commit")

    throughputs = [result.throughput_rps for result in runs]
    p95s = [result.latency.p95_seconds for result in runs]
    valid_runs = sum(result.valid for result in runs)
    dirty_runs = sum(result.git_dirty for result in runs)

    return BenchmarkAggregate(
        run_count=len(runs),
        valid_runs=valid_runs,
        median_throughput_rps=float(median(throughputs)),
        median_p95_seconds=float(median(p95s)),
        throughput_min_rps=min(throughputs),
        throughput_max_rps=max(throughputs),
        p95_min_seconds=min(p95s),
        p95_max_seconds=max(p95s),
        all_valid=valid_runs == len(runs),
        git_commit=next(iter(commits)),
        git_dirty_runs=dirty_runs,
    )
