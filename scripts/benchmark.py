#!/usr/bin/env python3
"""Phase 6 reproducible task/CRDT benchmark against the secure three-node cluster."""

from __future__ import annotations

import argparse
import asyncio
import ssl
from pathlib import Path

from distsys.benchmarking.model import BenchmarkConfig
from distsys.benchmarking.runner import BenchmarkRunner
from distsys.client import DistributedClient
from distsys.crdt_client import CrdtClient
from distsys.security.tls_context import build_client_context
from distsys.utils.config import Settings

_PORTS = (18000, 18001, 18002)


def _tls_settings(cert_dir: Path, identity: str) -> Settings:
    return Settings(
        request_timeout_seconds=5.0,
        tls_enabled=True,
        mtls_required=True,
        tls_ca_file=str(cert_dir / "ca" / "ca.crt"),
        tls_cert_file=str(cert_dir / identity / "node.crt"),
        tls_key_file=str(cert_dir / identity / "node.key"),
    )


def _task_client(port: int, ssl_context: ssl.SSLContext) -> DistributedClient:
    index = port - _PORTS[0]
    return DistributedClient(
        host="127.0.0.1",
        port=port,
        client_id="client",
        timeout_seconds=5.0,
        ssl_context=ssl_context,
        server_hostname=f"node-{index}",
    )


def _crdt_client(port: int, ssl_context: ssl.SSLContext) -> CrdtClient:
    index = port - _PORTS[0]
    return CrdtClient(
        host="127.0.0.1",
        port=port,
        client_id="crdt-client",
        timeout_seconds=5.0,
        ssl_context=ssl_context,
        server_hostname=f"node-{index}",
    )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=["quick", "laptop", "formal"],
        default="laptop",
    )
    parser.add_argument("--workload", choices=["task", "crdt"], default="task")
    parser.add_argument("--concurrency", type=int)
    parser.add_argument("--warmup", type=float)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--payload-size", type=int, default=256)
    parser.add_argument("--read-ratio", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=6)
    parser.add_argument("--cert-dir", type=Path, default=Path("certs/generated"))
    args = parser.parse_args()

    defaults = {
        "quick": (8, 1.0, 5.0),
        "laptop": (16, 10.0, 30.0),
        "formal": (16, 10.0, 30.0),
    }[args.profile]
    config = BenchmarkConfig(
        profile=args.profile,
        workload=args.workload,
        concurrency=args.concurrency or defaults[0],
        warmup_seconds=args.warmup if args.warmup is not None else defaults[1],
        duration_seconds=args.duration if args.duration is not None else defaults[2],
        payload_size=args.payload_size,
        read_ratio=args.read_ratio,
        seed=args.seed,
    )

    cert_dir = args.cert_dir.resolve()
    task_ssl = build_client_context(_tls_settings(cert_dir, "client"))
    crdt_ssl = build_client_context(_tls_settings(cert_dir, "crdt-client"))
    if task_ssl is None or crdt_ssl is None:
        raise RuntimeError("Phase 6 benchmark requires the Phase 5 mTLS development certificates")

    task_clients = [_task_client(port, task_ssl) for port in _PORTS]
    counter_key = f"phase6-benchmark-counter-{args.seed}"

    async def task_call(seq: int, payload: bytes) -> object:
        expected = {"seq": seq, "size": len(payload)}
        result = await task_clients[seq % len(task_clients)].request(
            "echo",
            expected,
            routing_key=str(seq),
        )
        if result != expected:
            raise AssertionError(f"echo mismatch: expected={expected!r}, got={result!r}")
        return result

    async def prepare_crdt_key() -> None:
        writer = _crdt_client(_PORTS[0], crdt_ssl)
        seeded = await writer.increment(counter_key)
        for port in _PORTS:
            reader = _crdt_client(port, crdt_ssl)
            observed = await reader.read(counter_key, causal_token=seeded.causal_token)
            if not isinstance(observed.value, int):
                raise TypeError(f"CRDT correctness failure on port {port}: {observed.value!r}")

    async def crdt_call(seq: int, is_read: bool) -> object:
        client = _crdt_client(_PORTS[seq % len(_PORTS)], crdt_ssl)
        result = await (client.read(counter_key) if is_read else client.increment(counter_key))
        if not isinstance(result.value, int):
            raise TypeError(f"CRDT correctness failure: {result.value!r}")
        return result

    if config.workload == "crdt":
        await prepare_crdt_key()

    result = await BenchmarkRunner(task_call=task_call, crdt_call=crdt_call).run(config)
    output_dir = Path("benchmark-results")
    output_dir.mkdir(exist_ok=True)
    filename = output_dir / (
        "phase6-" f"{result.timestamp_utc.replace(':', '').replace('-', '')}-" f"{config.seed}.json"
    )
    temporary = filename.with_suffix(".tmp")
    temporary.write_text(result.to_json() + "\n", encoding="utf-8")
    temporary.replace(filename)

    print(result.to_json())
    print(filename)
    budget_ok = result.success_ratio >= 0.99 and result.latency.p95_seconds < 0.5 and result.valid
    return 0 if budget_ok else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
