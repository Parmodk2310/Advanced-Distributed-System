from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "distributed-system"


def _read(relative: str) -> str:
    return (CHART / relative).read_text(encoding="utf-8")


def _yaml(relative: str) -> dict:
    loaded = yaml.safe_load(_read(relative))
    assert isinstance(loaded, dict)
    return loaded


def test_chart_has_versioned_profiles_and_schema() -> None:
    required = {
        "Chart.yaml",
        "values.yaml",
        "values-kind.yaml",
        "values-eks.yaml",
        "values-observability.yaml",
        "values.schema.json",
    }
    assert required <= {path.name for path in CHART.iterdir()}

    chart = _yaml("Chart.yaml")
    assert chart["version"] == "0.7.0"
    assert chart["appVersion"] == "0.6.0"


def test_safe_defaults_define_three_bounded_replicas() -> None:
    values = _yaml("values.yaml")

    assert values["replicaCount"] == 3
    assert values["crdt"]["replicationFactor"] == 3
    assert values["service"]["type"] == "ClusterIP"
    assert values["image"]["releaseMode"] is False
    assert values["resources"]["requests"] == {"cpu": "100m", "memory": "192Mi"}
    assert values["resources"]["limits"] == {"cpu": "500m", "memory": "512Mi"}


def test_statefulset_preserves_identity_storage_health_and_security() -> None:
    statefulset = _read("templates/statefulset.yaml")

    required_fragments = {
        "kind: StatefulSet",
        "serviceName:",
        "volumeClaimTemplates:",
        "PERSISTENCE_DB_PATH",
        "/data/node.db",
        "NODE_ID",
        "CLUSTER_SEEDS",
        "startupProbe:",
        "/health/live",
        "readinessProbe:",
        "/health/ready",
        "livenessProbe:",
        "runAsNonRoot: true",
        "runAsUser: 10001",
        "allowPrivilegeEscalation: false",
        "readOnlyRootFilesystem: true",
        "drop:",
        "- ALL",
        "seccompProfile:",
        "type: RuntimeDefault",
        "terminationGracePeriodSeconds:",
    }
    missing = sorted(fragment for fragment in required_fragments if fragment not in statefulset)
    assert not missing, missing


def test_chart_defines_internal_network_and_disruption_controls() -> None:
    services = _read("templates/services.yaml")
    policies = _read("templates/networkpolicy.yaml")
    pdb = _read("templates/pdb.yaml")

    assert "clusterIP: None" in services
    assert "name: protocol" in services
    assert "name: metrics" in services
    assert "policyTypes:" in policies
    assert "- Ingress" in policies
    assert "- Egress" in policies
    assert "kube-system" in policies
    assert "kind: PodDisruptionBudget" in pdb
    assert "minAvailable: 2" in pdb


def test_release_mode_requires_an_image_digest() -> None:
    helpers = _read("templates/_helpers.tpl")
    assert "releaseMode" in helpers
    assert "image.digest is required when image.releaseMode=true" in helpers
    assert 'fail "' in helpers


def test_chart_never_templates_private_key_material() -> None:
    rendered_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((CHART / "templates").glob("*"))
        if path.is_file()
    )

    assert "BEGIN PRIVATE KEY" not in rendered_sources
    assert "kind: Secret" not in rendered_sources
