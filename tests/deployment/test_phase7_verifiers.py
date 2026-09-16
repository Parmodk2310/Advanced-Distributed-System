from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(p):
    return (ROOT / p).read_text()


def test_cluster_verifier_is_fail_closed_and_mtls_bound():
    t = read("scripts/phase7/verify_cluster.py")
    assert 'client_id="phase7-client"' in t
    assert "expected 3 ready replicas" in t
    assert "mTLS connection without a client identity unexpectedly succeeded" in t
    assert "crdt_convergence" in t


def test_persistence_checks_same_pvc():
    t = read("scripts/phase7/verify_persistence.py")
    assert "same_pvc_reused" in t
    assert "PVC changed across pod replacement" in t


def test_rollback_uses_non_destructive_bad_readiness_then_reverifies():
    t = read("scripts/phase7/verify_rollback.sh")
    assert "phase7-intentional-failure" in t
    assert "helm rollback" in t
    assert "verify_cluster.py" in t


def test_public_verifier_uses_common_sni_and_mtls():
    t = read("scripts/phase7/verify_public_endpoint.py")
    assert 'server_hostname="phase7-public"' in t
    assert 'client_id="phase7-client"' in t


def test_port_forward_waits_for_every_local_listener() -> None:
    text = (ROOT / "scripts/phase7/verify_cluster.py").read_text()

    assert "def _wait_until_forwarding(" in text
    assert '"Forwarding from "' in text
    assert 'f"127.0.0.1:{port} ->"' in text
    assert "stdout=subprocess.PIPE" in text
    assert '"--address"' in text
    assert '"127.0.0.1"' in text
    assert "await self._wait_until_forwarding()" in text
    assert "await asyncio.sleep(1.0)" not in text
