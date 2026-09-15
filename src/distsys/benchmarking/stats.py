"""Small deterministic statistics helpers used by the benchmark runner."""

from __future__ import annotations

import math

from distsys.benchmarking.model import LatencySummary


def nearest_rank_percentile(samples: list[float] | tuple[float, ...], percentile: float) -> float:
    if not samples:
        raise ValueError("percentile requires at least one sample")
    if not 0.0 < percentile <= 1.0:
        raise ValueError("percentile must be in (0.0, 1.0]")
    ordered = sorted(float(value) for value in samples)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def latency_summary(samples: list[float] | tuple[float, ...]) -> LatencySummary:
    if not samples:
        return LatencySummary(0.0, 0.0, 0.0, 0.0)
    return LatencySummary(
        p50_seconds=nearest_rank_percentile(samples, 0.50),
        p95_seconds=nearest_rank_percentile(samples, 0.95),
        p99_seconds=nearest_rank_percentile(samples, 0.99),
        max_seconds=max(samples),
    )
