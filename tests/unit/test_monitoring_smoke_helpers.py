from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def load_monitoring_smoke():
    path = Path("scripts/phase6_monitoring_smoke.py")
    spec = spec_from_file_location("phase6_monitoring_smoke", path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def target_snapshot(healthy_count: int) -> dict[str, object]:
    targets = [
        {
            "health": "up",
            "labels": {"job": "distsys-phase6"},
        }
        for _ in range(healthy_count)
    ]
    return {"data": {"activeTargets": targets}}


def test_prometheus_wait_retries_until_all_three_targets_are_healthy(
    monkeypatch,
) -> None:
    smoke = load_monitoring_smoke()
    responses = iter([target_snapshot(2), target_snapshot(3)])
    monkeypatch.setattr(smoke, "fetch_json", lambda _url: next(responses))
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)

    healthy = smoke.wait_for_healthy_prometheus_targets(seconds=1.0)

    assert len(healthy) == 3
