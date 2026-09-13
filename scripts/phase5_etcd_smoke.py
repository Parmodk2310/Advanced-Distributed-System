#!/usr/bin/env python3
"""Verify data-plane survival across a managed etcd outage and recovery."""

from __future__ import annotations

import argparse
import asyncio
import os
import ssl
import time
from pathlib import Path

from distsys.coordination.errors import CoordinationUnavailableError
from distsys.coordination.etcd_client import EtcdGatewayCoordinationClient
from distsys.crdt_client import CrdtClient


async def run_docker_compose(compose: Path, *args: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "-f",
        str(compose),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"docker compose {' '.join(args)} failed: {detail}")


def tls_context(cert_dir: Path) -> ssl.SSLContext:
    context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile=str(cert_dir / "ca" / "ca.crt"),
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(
        str(cert_dir / "crdt-client" / "node.crt"),
        str(cert_dir / "crdt-client" / "node.key"),
    )
    return context


async def wait_for_registrations(expected: set[str], timeout: float) -> None:
    endpoints = tuple(
        item.strip()
        for item in os.getenv("ETCD_ENDPOINTS", "http://127.0.0.1:2379").split(",")
        if item.strip()
    )
    namespace = os.getenv("ETCD_NAMESPACE", "/distsys/v1")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        client = EtcdGatewayCoordinationClient(endpoints, namespace=namespace)
        try:
            await client.connect()
            members = await client.discover_members()
            if {m.node_id for m in members} >= expected:
                return
        except (CoordinationUnavailableError, ConnectionError, OSError, TimeoutError):
            pass
        finally:
            await client.close()
        await asyncio.sleep(0.4)
    raise TimeoutError("etcd member registrations did not recover")


async def main_async(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    compose = root / "docker" / "etcd" / "docker-compose.yml"
    cert_dir = Path(args.cert_dir).resolve()

    await run_docker_compose(compose, "stop", "etcd")
    await asyncio.sleep(float(args.outage_wait))

    client = CrdtClient(
        port=18000,
        timeout_seconds=5,
        ssl_context=tls_context(cert_dir),
        server_hostname="node-0",
    )
    key = f"phase5.etcd.outage.{time.time_ns()}"
    result = await client.increment(key)
    if result.value != 1:
        raise AssertionError("data-plane write failed during etcd outage")
    read = await client.read(key, causal_token=result.causal_token)
    if read.value != 1:
        raise AssertionError("data-plane read failed during etcd outage")
    print("phase5_etcd_degraded_data_plane=PASS")

    await run_docker_compose(compose, "start", "etcd")
    await wait_for_registrations({"node-0", "node-1", "node-2"}, timeout=15)
    print("phase5_etcd_registration_recovered=PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert-dir", default="certs/generated")
    parser.add_argument("--outage-wait", default="3.0")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
