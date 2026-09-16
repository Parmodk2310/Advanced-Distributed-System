from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cluster_verifier_is_bounded_and_checks_security() -> None:
    text = (ROOT / "scripts/phase7/verify_cluster.py").read_text()
    assert "timeout=timeout" in text
    assert "forwarded endpoint did not become ready" in text
    assert "ready != 3" in text
    assert "mTLS connection without a client identity" in text
    assert '"crdt_convergence": "pass"' in text


def test_persistence_verifier_restarts_pod_and_uses_causal_token() -> None:
    text = (ROOT / "scripts/phase7/verify_persistence.py").read_text()
    assert '"delete", "pod"' in text
    assert '"--for=condition=Ready"' in text
    assert "causal_token=written.causal_token" in text
    assert "persistent value mismatch" in text


def test_rollback_is_fail_closed_and_reverifies() -> None:
    text = (ROOT / "scripts/phase7/verify_rollback.sh").read_text()
    assert "set -euo pipefail" in text
    assert "expected deliberately unhealthy upgrade to fail" in text
    assert "helm rollback" in text
    assert "verify_cluster.py" in text
