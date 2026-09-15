from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "phase7"


def _read(relative: str) -> str:
    path = ROOT / relative
    assert path.is_file(), f"missing Phase 7 file: {relative}"
    return path.read_text(encoding="utf-8")


def test_all_phase7_shell_scripts_are_valid_strict_bash() -> None:
    scripts = sorted(SCRIPTS.glob("*.sh"))
    assert scripts

    for script in scripts:
        content = script.read_text(encoding="utf-8")
        assert content.startswith("#!/usr/bin/env bash\nset -euo pipefail\n")
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_workspace_and_cluster_names_are_fixed_and_narrow() -> None:
    common = _read("scripts/phase7/common.sh")
    cleanup = _read("scripts/phase7/cluster_down.sh")

    assert 'PHASE7_WORK_DIR="$PHASE7_REPO_ROOT/.phase7"' in common
    assert "PHASE7_KIND_CLUSTER:-distsys-phase7" in common
    assert "PHASE7_K3D_CLUSTER:-distsys-phase7-k3d" in common
    assert 'test "$PHASE7_REPO_ROOT" != "/"' in common
    assert 'rm -rf "$PHASE7_WORK_DIR"' in cleanup
    assert "rm -rf /" not in cleanup
    assert 'rm -rf "$PHASE7_REPO_ROOT"' not in cleanup


def test_cluster_creation_is_failure_safe() -> None:
    kind = _read("scripts/phase7/cluster_up.sh")
    k3d = _read("scripts/phase7/k3d_verify.sh")

    assert "trap cleanup_on_exit EXIT INT TERM" in kind
    assert "print_failure_diagnostics" in kind
    assert "--all-containers --prefix --tail=100" in kind
    assert "cleanup_required=0" in kind
    assert "PHASE7_SKIP_BUILD:-0" in kind
    assert "trap cleanup EXIT INT TERM" in k3d
    assert "optional parity check skipped" in k3d
    assert "values-kind.yaml" in kind and "values-kind.yaml" in k3d


def test_tls_generation_uses_per_pod_sans_and_never_persists_secret_yaml() -> None:
    script = _read("scripts/phase7/generate_tls_secret.sh")

    assert 'chmod 600 "$TLS_DIR/ca/ca.key"' in script
    assert 'chmod 600 "$identity_dir/tls.key"' in script
    assert "phase7-distributed-system-$ordinal" not in script
    assert "$PHASE7_RELEASE-distributed-system-$ordinal" in script
    assert "subjectAltName=DNS:$identity" in script
    assert "--dry-run=client -o yaml | kubectl apply -f -" in script
    assert "> secret.yaml" not in script
    assert "BEGIN PRIVATE KEY" not in script


def test_local_cluster_configs_are_laptop_safe_and_pinned() -> None:
    kind = yaml.safe_load(_read("deploy/kind/cluster.yaml"))
    k3d = yaml.safe_load(_read("deploy/k3d/cluster.yaml"))
    etcd = _read("deploy/kind/etcd.yaml")

    assert kind["name"] == "distsys-phase7"
    assert kind["nodes"] == [{"role": "control-plane"}]
    assert k3d["metadata"]["name"] == "distsys-phase7-k3d"
    assert k3d["servers"] == 1 and k3d["agents"] == 0
    assert "quay.io/coreos/etcd:v3.5.15@sha256:" in etcd
    assert "runAsNonRoot: true" in etcd
    assert "readOnlyRootFilesystem: true" in etcd


def test_statefulset_selects_a_distinct_certificate_for_each_pod() -> None:
    statefulset = _read("deploy/helm/distributed-system/templates/statefulset.yaml")

    assert "name: select-node-identity" in statefulset
    assert "${NODE_ID}.crt" in statefulset
    assert "${NODE_ID}.key" in statefulset
    assert "name: tls-source" in statefulset
    assert "name: tls-runtime" in statefulset
    assert "medium: Memory" in statefulset
