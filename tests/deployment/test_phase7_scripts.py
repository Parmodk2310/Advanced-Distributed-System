from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PHASE7 = ROOT / "scripts" / "phase7"
KIND_CONFIG = ROOT / "deploy" / "kind" / "cluster.yaml"


def _script(name: str) -> str:
    return (PHASE7 / name).read_text(encoding="utf-8")


def test_kind_cluster_is_small_and_has_no_ingress_mapping() -> None:
    config = yaml.safe_load(KIND_CONFIG.read_text(encoding="utf-8"))

    assert config["kind"] == "Cluster"
    assert config["nodes"] == [{"role": "control-plane"}]
    assert "extraPortMappings" not in config["nodes"][0]


def test_common_helpers_pin_safe_workspace_and_names() -> None:
    script = _script("common.sh")

    assert "set -euo pipefail" in script
    assert 'PHASE7_CLUSTER_NAME="distsys-phase7"' in script
    assert 'PHASE7_NAMESPACE="distsys"' in script
    assert 'PHASE7_WORK_DIR="$PHASE7_REPO_ROOT/.phase7"' in script
    assert 'case "$PHASE7_WORK_DIR"' in script
    assert "refusing unsafe Phase 7 workspace" in script


def test_cluster_up_always_registers_cleanup() -> None:
    script = _script("cluster_up.sh")

    assert "set -euo pipefail" in script
    assert "trap cleanup_on_error ERR INT TERM" in script
    assert "kind create cluster" in script
    assert "kind load docker-image" in script
    assert "helm upgrade --install" in script
    assert re.search(r"kubectl\\s+(?:-n \"\\$PHASE7_NAMESPACE\"\\s+)?rollout status", script)


def test_cluster_down_is_idempotent_and_removes_tls_material() -> None:
    script = _script("cluster_down.sh")

    assert "set -euo pipefail" in script
    assert "kind delete cluster" in script
    assert 'safe_remove_dir "$PHASE7_TLS_DIR"' in script


def test_tls_secret_is_streamed_without_persisted_manifest() -> None:
    script = _script("generate_tls_secret.sh")

    assert "set -euo pipefail" in script
    assert "umask 077" in script
    assert "chmod 600" in script
    assert re.search(r"kubectl\\s+-n \"\\$PHASE7_NAMESPACE\"\\s+create secret generic", script)
    assert "--dry-run=client -o yaml" in script
    assert "| kubectl apply -f -" in script
    assert "> secret.yaml" not in script
    assert "BEGIN PRIVATE KEY" not in script


def test_generated_phase7_workspace_is_gitignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".phase7/" in ignored
