#!/usr/bin/env python3
"""End-to-end Phase 6 monitoring smoke, including one exported distributed trace."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import urllib.request
from pathlib import Path

from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.peer_client import PeerClient
from distsys.observability.tracing import TracingRuntime
from distsys.resilience.retry import RetryPolicy
from distsys.security.tls_context import build_client_context
from distsys.utils.config import Settings


def fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=4) as response:
        return json.loads(response.read())


def fetch_status(url: str) -> int:
    with urllib.request.urlopen(url, timeout=4) as response:
        response.read()
        return response.status


def wait_json(url: str, seconds: float = 30.0):
    deadline = time.monotonic() + seconds
    last: BaseException | None = None
    while time.monotonic() < deadline:
        try:
            return fetch_json(url)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.5)
    raise RuntimeError(f"timed out waiting for {url}: {last}")


async def emit_trace(cert_dir: Path) -> str:
    settings = Settings(
        tls_enabled=True,
        mtls_required=True,
        tls_ca_file=str(cert_dir / "ca" / "ca.crt"),
        tls_cert_file=str(cert_dir / "node-0" / "node.crt"),
        tls_key_file=str(cert_dir / "node-0" / "node.key"),
        tracing_enabled=True,
        otel_exporter_otlp_endpoint="http://127.0.0.1:4318",
        otel_service_name="phase6-smoke",
        otel_trace_sample_ratio=1.0,
        otel_export_timeout_seconds=2.0,
    )
    tracing = TracingRuntime.create(settings, "phase6-smoke")
    peer = PeerClient(
        local_node_id="node-0",
        retry_policy=RetryPolicy(
            max_attempts=1,
            base_delay_seconds=0,
            max_delay_seconds=0,
        ),
        circuit_breaker_failure_threshold=2,
        circuit_breaker_recovery_seconds=1.0,
        ssl_context=build_client_context(settings),
    )
    peer.tracing = tracing
    target = ClusterMember(
        node_id="node-1",
        host="127.0.0.1",
        port=18001,
        status=MemberStatus.ALIVE,
        incarnation=1,
    )
    trace_id = ""
    with tracing.tracer.start_as_current_span("phase6.monitoring.smoke") as span:
        trace_id = f"{span.get_span_context().trace_id:032x}"
        ack = await peer.ping(target, (), timeout_seconds=3.0)
        if not ack.success:
            raise RuntimeError("cross-node traced ping did not return ACK")
    await tracing.shutdown(2.0)
    return trace_id


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert-dir", type=Path, default=Path("certs/generated"))
    args = parser.parse_args()

    targets = await asyncio.to_thread(wait_json, "http://127.0.0.1:9090/api/v1/targets")
    active = targets["data"]["activeTargets"]
    healthy = [
        target
        for target in active
        if target.get("health") == "up" and target.get("labels", {}).get("job") == "distsys-phase6"
    ]
    if len(healthy) != 3:
        raise SystemExit(f"expected 3 healthy Prometheus node targets, got {len(healthy)}")

    grafana = await asyncio.to_thread(wait_json, "http://127.0.0.1:3000/api/health")
    if grafana.get("database") != "ok":
        raise SystemExit("Grafana database is not healthy")
    dashboard = await asyncio.to_thread(
        wait_json, "http://127.0.0.1:3000/api/dashboards/uid/distsys-phase6"
    )
    if dashboard.get("dashboard", {}).get("uid") != "distsys-phase6":
        raise SystemExit("provisioned Phase 6 dashboard is missing")
    if await asyncio.to_thread(fetch_status, "http://127.0.0.1:3200/ready") != 200:
        raise SystemExit("Tempo is not ready")

    trace_id = await emit_trace(args.cert_dir.resolve())
    deadline = time.monotonic() + 15.0
    trace = None
    while time.monotonic() < deadline:
        try:
            trace = await asyncio.to_thread(
                fetch_json,
                f"http://127.0.0.1:3200/api/traces/{trace_id}",
            )
            break
        except Exception:  # noqa: BLE001 - Tempo may not have indexed the trace yet
            await asyncio.sleep(0.5)
    if trace is None:
        raise SystemExit(f"Tempo did not return emitted trace {trace_id}")
    resource_spans = trace.get("batches") or trace.get("resourceSpans") or []
    if not resource_spans:
        raise SystemExit("Tempo trace response contains no spans")
    print(
        "Phase 6 monitoring smoke passed: "
        f"Prometheus=3/3, Grafana provisioned, Tempo trace={trace_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
