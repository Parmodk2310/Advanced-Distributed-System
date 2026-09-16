import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "phase7"


def read(p):
    return (ROOT / p).read_text()


def test_shell_scripts_use_strict_mode_and_parse():
    scripts = sorted(SCRIPTS.glob("*.sh"))
    assert scripts
    for script in scripts:
        text = script.read_text()
        assert text.startswith("#!/usr/bin/env bash\nset -euo pipefail\n")
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_kind_topology_is_one_control_plane_two_workers():
    cfg = yaml.safe_load(read("deploy/kind/cluster.yaml"))
    assert cfg["nodes"] == [{"role": "control-plane"}, {"role": "worker"}, {"role": "worker"}]


def test_local_etcd_is_single_lightweight_dev_instance():
    text = read("deploy/kind/etcd.yaml")
    assert "replicas: 1" in text
    assert "emptyDir:" in text
    assert "quay.io/coreos/etcd:v3.5.15@sha256:" in text
    assert "runAsNonRoot: true" in text


def test_tls_is_ephemeral_and_has_public_demo_sni_name():
    text = read("scripts/phase7/generate_tls_secret.sh")
    assert 'chmod 600 "$TLS_DIR/ca/ca.key"' in text
    assert "--dry-run=client -o yaml | kubectl apply -f -" in text
    assert "DNS:phase7-public" in text
    assert "> secret.yaml" not in text
