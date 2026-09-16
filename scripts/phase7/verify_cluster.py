#!/usr/bin/env python3
"""Live Phase 7 kind/k3d verification with sanitized JSON evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import ssl
import subprocess
import time
import urllib.request
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Self

from distsys.crdt_client import CrdtClient

ROOT = Path(__file__).resolve().parents[2]


def run(*args: str, timeout: float = 30.0) -> str:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()[:2000]
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(args)}\n{detail}")
    return completed.stdout.strip()


def wait_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"port-forward did not open localhost:{port}")


class PortForward:
    def __init__(self, namespace: str, pod: str, mappings: tuple[str, ...]) -> None:
        self.namespace = namespace
        self.pod = pod
        self.mappings = mappings
        self.process: subprocess.Popen[str] | None = None

    def _start(self) -> subprocess.Popen[str]:
        return subprocess.Popen(
            ["kubectl", "-n", self.namespace, "port-forward", f"pod/{self.pod}", *self.mappings],
            cwd=ROOT,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    async def __aenter__(self) -> Self:
        self.process = await asyncio.to_thread(self._start)
        # A raw TCP readiness probe can make kubectl tear down a forwarding
        # stream before an application protocol request is sent. Give kubectl
        # a bounded startup window and let the real HTTP/client checks retry.
        await asyncio.sleep(1.0)
        if self.process.poll() is not None:
            detail = self.process.stderr.read().strip()[:2000] if self.process.stderr else ""
            raise RuntimeError(f"kubectl port-forward exited early: {detail}")
        return self

    async def __aexit__(self, *_: object) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            await asyncio.to_thread(self.process.wait, 5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            await asyncio.to_thread(self.process.wait, 5)


def tls_context(work_dir: Path) -> ssl.SSLContext:
    tls = work_dir / "tls"
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(tls / "ca/ca.crt"))
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(
        str(tls / "phase7-client/tls.crt"),
        str(tls / "phase7-client/tls.key"),
    )
    return context


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=3) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise TypeError("health response must be a JSON object")
    return value


def get_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.read().decode("utf-8")


async def wait_http(url: str, *, json_response: bool, timeout: float = 15.0) -> Any:
    """Wait until the forwarded backend, not only the local socket, responds."""
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            function = get_json if json_response else get_text
            return await asyncio.to_thread(function, url)
        except OSError as exc:
            last_error = exc
            await asyncio.sleep(0.2)
    raise TimeoutError(f"forwarded endpoint did not become ready: {url}") from last_error


async def verify(namespace: str, release: str, work_dir: Path) -> dict[str, Any]:
    statefulset = json.loads(
        run(
            "kubectl",
            "-n",
            namespace,
            "get",
            "statefulset",
            f"{release}-distributed-system",
            "-o",
            "json",
        )
    )
    ready = int(statefulset.get("status", {}).get("readyReplicas", 0))
    if ready != 3:
        raise AssertionError(f"expected 3 ready replicas, got {ready}")

    pod0 = f"{release}-distributed-system-0"
    pod2 = f"{release}-distributed-system-2"
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(PortForward(namespace, pod0, ("18000:8000", "19100:9100")))
        await stack.enter_async_context(PortForward(namespace, pod2, ("18002:8000", "19102:9100")))

        for port in (19100, 19102):
            health = await wait_http(f"http://127.0.0.1:{port}/health/ready", json_response=True)
            if not health.get("readiness"):
                raise AssertionError(f"node on observability port {port} is not ready")
            metrics = await wait_http(f"http://127.0.0.1:{port}/metrics", json_response=False)
            if "distsys_requests_total" not in metrics:
                raise AssertionError("expected distsys_requests_total metric")

        context = tls_context(work_dir)
        key = f"phase7.verify.{time.time_ns()}"
        writer = CrdtClient(
            port=18000,
            client_id="phase7-client",
            timeout_seconds=5,
            ssl_context=context,
            server_hostname=pod0,
        )
        written = await writer.increment(key, amount=2)
        reader = CrdtClient(
            port=18002,
            client_id="phase7-client",
            timeout_seconds=5,
            ssl_context=context,
            server_hostname=pod2,
        )
        observed = await reader.read(key, causal_token=written.causal_token)
        if observed.value != 2:
            raise AssertionError(f"cross-node CRDT value mismatch: {observed.value!r}")

        no_identity = ssl.create_default_context(
            ssl.Purpose.SERVER_AUTH, cafile=str(work_dir / "tls/ca/ca.crt")
        )
        no_identity.minimum_version = ssl.TLSVersion.TLSv1_3
        rejected = False
        try:
            await CrdtClient(
                port=18000,
                client_id="phase7-client",
                timeout_seconds=2,
                ssl_context=no_identity,
                server_hostname=pod0,
            ).read("phase7.untrusted")
        except (ssl.SSLError, ConnectionError, OSError, asyncio.IncompleteReadError):
            rejected = True
        if not rejected:
            raise AssertionError("mTLS connection without a client identity unexpectedly succeeded")

    return {
        "schema_version": 1,
        "commit": run("git", "rev-parse", "HEAD") if (ROOT / ".git").exists() else "workspace",
        "chart_version": "0.7.0",
        "ready_replicas": ready,
        "health": "pass",
        "metrics": "pass",
        "mtls_rejection": "pass",
        "crdt_convergence": "pass",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default="distsys")
    parser.add_argument("--release", default="phase7")
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".phase7")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    evidence = await verify(args.namespace, args.release, args.work_dir.resolve())
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    asyncio.run(main())
