#!/usr/bin/env python3
"""Verify the temporary external TCP endpoint using the ephemeral Phase 7 mTLS client."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import socket
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


async def wait_for_endpoint(
    host: str,
    port: int,
    *,
    timeout_seconds: float,
    poll_interval: float,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    last_error: OSError | TimeoutError | None = None

    print(f"waiting for public endpoint readiness: {host}:{port}")
    while loop.time() < deadline:
        writer: asyncio.StreamWriter | None = None
        try:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.wait_for(
                asyncio.to_thread(
                    socket.getaddrinfo,
                    host,
                    port,
                    type=socket.SOCK_STREAM,
                ),
                timeout=remaining,
            )

            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=min(5.0, remaining),
            )
            return
        except (OSError, TimeoutError) as exc:
            last_error = exc
        finally:
            if writer is not None:
                writer.close()
                remaining = deadline - loop.time()
                if remaining > 0:
                    with contextlib.suppress(OSError, TimeoutError):
                        await asyncio.wait_for(
                            writer.wait_closed(),
                            timeout=remaining,
                        )

        remaining = deadline - loop.time()
        if remaining > 0:
            await asyncio.sleep(min(poll_interval, remaining))

    raise TimeoutError(
        f"public endpoint was not ready after {timeout_seconds:g}s: "
        f"{host}:{port}; last error: {last_error!r}"
    )


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--readiness-timeout", type=float, default=300)
    p.add_argument("--poll-interval", type=float, default=5)
    p.add_argument("--work-dir", type=Path, default=ROOT / ".phase7")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.readiness_timeout <= 0 or a.poll_interval <= 0:
        p.error("readiness timeout and poll interval must be positive")

    await wait_for_endpoint(
        a.host,
        a.port,
        timeout_seconds=a.readiness_timeout,
        poll_interval=a.poll_interval,
    )

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
