"""Correctness-aware Phase 6 benchmark support."""

from distsys.benchmarking.aggregate import BenchmarkAggregate, aggregate_runs
from distsys.benchmarking.model import BenchmarkConfig, BenchmarkResult
from distsys.benchmarking.runner import BenchmarkRunner

__all__ = [
    "BenchmarkAggregate",
    "BenchmarkConfig",
    "BenchmarkResult",
    "BenchmarkRunner",
    "aggregate_runs",
]
