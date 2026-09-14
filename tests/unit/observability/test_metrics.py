from prometheus_client import CollectorRegistry

from distsys.observability.metrics import Metrics


def test_registries_are_isolated_and_unknown_labels_normalize():
    left = Metrics("node-a")
    right = Metrics("node-b")
    assert isinstance(left.registry, CollectorRegistry)
    assert left.registry is not right.registry

    left.request_finished("totally-dynamic", "mystery", 0.012)
    text = left.render().decode()
    assert 'message_type="other"' in text
    assert 'status="other"' in text
    assert "totally-dynamic" not in text
    assert "mystery" not in text
    assert "node-b" not in text


def test_request_inflight_and_histogram_are_recorded():
    metrics = Metrics("node-a")
    metrics.request_started("task")
    metrics.request_finished("task", "success", 0.025)
    text = metrics.render().decode()
    assert (
        'distsys_requests_total{message_type="task",node_id="node-a",'
        'status="success"} 1.0' in text
    )
    assert 'distsys_requests_inflight{node_id="node-a"} 0.0' in text
    assert (
        'distsys_request_duration_seconds_count{message_type="task",'
        'node_id="node-a"} 1.0' in text
    )


def test_disabled_metrics_are_safe_noops():
    metrics = Metrics("node-a", enabled=False)
    metrics.request_started("task")
    metrics.request_finished("task", "success", 1.0)
    metrics.peer_rpc("ping", "error", 0.1)
    assert metrics.render() == b""
