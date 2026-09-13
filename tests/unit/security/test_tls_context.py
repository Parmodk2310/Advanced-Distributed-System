import ssl
import subprocess
from pathlib import Path

from distsys.security.tls_context import build_client_context, build_server_context
from distsys.utils.config import Settings


def _settings(tmp_path: Path) -> Settings:
    out = tmp_path / "certs"
    subprocess.run(
        ["bash", "scripts/generate_dev_certs.sh", str(out)], check=True, capture_output=True
    )
    return Settings(
        tls_enabled=True,
        mtls_required=True,
        tls_ca_file=str(out / "ca" / "ca.crt"),
        tls_cert_file=str(out / "node-0" / "node.crt"),
        tls_key_file=str(out / "node-0" / "node.key"),
    )


def test_disabled_tls_returns_no_context():
    assert build_server_context(Settings()) is None
    assert build_client_context(Settings()) is None


def test_secure_contexts_require_tls13_and_mutual_auth(tmp_path):
    settings = _settings(tmp_path)
    server = build_server_context(settings)
    client = build_client_context(settings)
    assert server is not None and client is not None
    assert server.minimum_version is ssl.TLSVersion.TLSv1_3
    assert server.verify_mode is ssl.CERT_REQUIRED
    assert client.minimum_version is ssl.TLSVersion.TLSv1_3
