#!/usr/bin/env python3
"""Verify the temporary external TCP endpoint using the ephemeral Phase 7 mTLS client."""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import time
from pathlib import Path

from distsys.crdt_client import CrdtClient

ROOT = Path(__file__).resolve().parents[2]


def context(work_dir: Path) -> ssl.SSLContext:
    tls = work_dir / "tls"
    c = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(tls / "ca/ca.crt"))
    c.minimum_version = ssl.TLSVersion.TLSv1_3
    c.load_cert_chain(str(tls / "phase7-client/tls.crt"), str(tls / "phase7-client/tls.key"))
    return c


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--work-dir", type=Path, default=ROOT / ".phase7")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    client = CrdtClient(
        host=a.host,
        port=a.port,
        client_id="phase7-client",
        timeout_seconds=10,
        ssl_context=context(a.work_dir),
        server_hostname="phase7-public",
    )
    key = f"phase7.public.{time.time_ns()}"
    written = await client.increment(key, amount=1)
    observed = await client.read(key, causal_token=written.causal_token)
    if observed.value != 1:
        raise AssertionError(f"external CRDT mismatch: {observed.value!r}")
    evidence = {"schema_version": 1, "external_endpoint": "pass", "mtls": "pass", "crdt": "pass"}
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    asyncio.run(main())
