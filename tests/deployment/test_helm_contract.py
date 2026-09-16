from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "distributed-system"


def _read(relative: str) -> str:
    path = CHART / relative
    assert path.is_file(), f"missing Helm file: {relative}"
    return path.read_text(encoding="utf-8")


def _values(name: str = "values.yaml") -> dict[str, object]:
    loaded = yaml.safe_load(_read(name))
    assert isinstance(loaded, dict)
    return loaded


def test_chart_versions_and_profiles_are_explicit() -> None:
    metadata = yaml.safe_load(_read("Chart.yaml"))

    assert metadata["version"] == "0.7.0"
    assert metadata["appVersion"] == "0.6.0"
    assert metadata["kubeVersion"] == ">=1.29.0-0"
    assert (CHART / "values-kind.yaml").is_file()
    assert (CHART / "values-eks.yaml").is_file()
    assert (CHART / "values-observability.yaml").is_file()


def test_safe_defaults_define_three_durable_nodes() -> None:
    values = _values()

    assert values["replicaCount"] == 3
    assert values["cluster"]["replicationFactor"] == 3  # type: ignore[index]
    assert values["publicEndpoint"]["enabled"] is False  # type: ignore[index]
    assert values["resources"] == {  # type: ignore[comparison-overlap]
        "requests": {"cpu": "100m", "memory": "192Mi"},
        "limits": {"cpu": "500m", "memory": "512Mi"},
    }
    assert values["podDisruptionBudget"]["minAvailable"] == 2  # type: ignore[index]


def test_release_mode_requires_sha256_digest() -> None:
    helpers = _read("templates/_helpers.tpl")
    schema = json.loads(_read("values.schema.json"))

    assert 'required "image.repository is required in release mode"' in helpers
    assert 'required "image.digest is required in release mode"' in helpers
    assert 'printf "%s@%s" $repository $digest' in helpers
    digest = schema["properties"]["image"]["properties"]["digest"]
    assert digest["pattern"] == "^$|^sha256:[0-9a-f]{64}$"


def test_statefulset_enforces_identity_health_and_security() -> None:
    statefulset = _read("templates/statefulset.yaml")

    required = (
        "kind: StatefulSet",
        "fieldPath: metadata.name",
        "volumeClaimTemplates:",
        "path: /health/live",
        "path: /health/ready",
        "runAsNonRoot: true",
        "runAsUser: 10001",
        "allowPrivilegeEscalation: false",
        "readOnlyRootFilesystem: true",
        'drop: ["ALL"]',
        "type: RuntimeDefault",
        "terminationGracePeriodSeconds:",
    )
    for fragment in required:
        assert fragment in statefulset


def test_chart_defines_internal_services_pdb_and_network_boundaries() -> None:
    services = _read("templates/services.yaml")
    pdb = _read("templates/pdb.yaml")
    network = _read("templates/networkpolicy.yaml")

    assert "clusterIP: None" in services
    assert "type: ClusterIP" in services
    assert "type: LoadBalancer" not in services
    assert "kind: PodDisruptionBudget" in pdb
    assert "minAvailable:" in pdb
    assert "default-deny" in network
    assert 'policyTypes: ["Ingress", "Egress"]' in network
    for port in ("port: 53", "port: 2379", "port: 4318"):
        assert port in network


def test_runtime_configuration_matches_existing_environment_contract() -> None:
    configmap = _read("templates/configmap.yaml")
    statefulset = _read("templates/statefulset.yaml")

    for variable in (
        "NODE_PORT",
        "CLUSTER_SEEDS",
        "CRDT_REPLICATION_FACTOR",
        "PERSISTENCE_DB_PATH",
        "ETCD_ENDPOINTS",
        "TLS_CA_FILE",
        "TLS_CERT_FILE",
        "TLS_KEY_FILE",
        "OBSERVABILITY_PORT",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        assert variable in configmap
    assert "- name: NODE_HOST" in statefulset
    assert "fieldPath: metadata.name" in statefulset
    assert 'NODE_HOST: "0.0.0.0"' not in configmap


def test_chart_never_renders_private_key_material() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in CHART.rglob("*.*"))

    assert "BEGIN PRIVATE KEY" not in combined
    assert "BEGIN RSA PRIVATE KEY" not in combined
    assert "tls.key:" not in combined
