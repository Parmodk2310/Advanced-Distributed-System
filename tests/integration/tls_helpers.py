from __future__ import annotations

import ssl
import subprocess
from pathlib import Path


def generate_dev_certs(root: Path) -> Path:
    output = root / "certs"
    subprocess.run(
        ["bash", "scripts/generate_dev_certs.sh", str(output)],
        check=True,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
    return output


def client_context(certs: Path, identity: str) -> ssl.SSLContext:
    context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile=str(certs / "ca" / "ca.crt"),
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(
        str(certs / identity / "node.crt"),
        str(certs / identity / "node.key"),
    )
    return context
