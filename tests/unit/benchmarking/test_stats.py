import pytest

from distsys.benchmarking.stats import latency_summary, nearest_rank_percentile


def test_nearest_rank_percentile_boundaries():
    assert nearest_rank_percentile([1.0], 0.50) == 1.0
    assert nearest_rank_percentile([4.0, 1.0, 3.0, 2.0], 0.50) == 2.0
    assert nearest_rank_percentile([4.0, 1.0, 3.0, 2.0], 0.95) == 4.0
    with pytest.raises(ValueError):
        nearest_rank_percentile([], 0.50)
    with pytest.raises(ValueError):
        nearest_rank_percentile([1.0], 0.0)


def test_latency_summary_reports_required_percentiles():
    summary = latency_summary([0.1, 0.2, 0.3, 0.4])
    assert summary.p50_seconds == 0.2
    assert summary.p95_seconds == 0.4
    assert summary.p99_seconds == 0.4
    assert summary.max_seconds == 0.4
