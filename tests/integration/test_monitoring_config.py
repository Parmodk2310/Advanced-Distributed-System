import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_monitoring_stack_is_pinned_scoped_and_laptop_safe():
    compose = yaml.safe_load((ROOT / "deploy/monitoring/docker-compose.yml").read_text())
    services = compose["services"]
    assert services["prometheus"]["image"] == "prom/prometheus:v3.13.3"
    assert services["grafana"]["image"] == "grafana/grafana:13.2.1"
    assert services["tempo"]["image"] == "grafana/tempo:3.0.2"
    assert services["toxiproxy"]["image"] == "ghcr.io/shopify/toxiproxy:2.12.0"
    assert "loki" not in services
    assert "--storage.tsdb.retention.time=2h" in services["prometheus"]["command"]
    for service in services.values():
        assert "logging" in service


def test_prometheus_targets_and_grafana_provisioning_are_complete():
    prometheus = yaml.safe_load((ROOT / "deploy/monitoring/prometheus/prometheus.yml").read_text())
    targets = prometheus["scrape_configs"][0]["static_configs"][0]["targets"]
    assert targets == [
        "host.docker.internal:9100",
        "host.docker.internal:9101",
        "host.docker.internal:9102",
    ]
    datasources = yaml.safe_load(
        (ROOT / "deploy/monitoring/grafana/provisioning/datasources/datasources.yml").read_text()
    )["datasources"]
    assert {d["uid"] for d in datasources} == {"prometheus", "tempo"}
    dashboard = json.loads(
        (ROOT / "deploy/monitoring/grafana/dashboards/phase6-overview.json").read_text()
    )
    assert dashboard["uid"] == "distsys-phase6"
    titles = {panel["title"] for panel in dashboard["panels"]}
    assert {
        "Node readiness",
        "Request throughput",
        "Replication queue",
        "Coordination health",
        "Recovery phase",
    } <= titles
    assert all(panel.get("description") for panel in dashboard["panels"])


def test_tempo_3_compaction_schema_preserves_two_hour_retention():
    tempo = yaml.safe_load((ROOT / "deploy/monitoring/tempo/tempo.yml").read_text())
    assert "compactor" not in tempo
    assert (
        tempo["backend_scheduler"]["provider"]["compaction"]["compaction"]["block_retention"]
        == "2h"
    )
    assert tempo["backend_worker"]["compaction"]["block_retention"] == "2h"
