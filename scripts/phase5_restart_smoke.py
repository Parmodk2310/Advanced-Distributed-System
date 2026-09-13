#!/usr/bin/env python3
"""Managed restart/recovery smoke for a running Phase-5 cluster."""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sqlite3
import ssl
import sys
import time
from pathlib import Path

from distsys.coordination.errors import CoordinationUnavailableError
from distsys.coordination.etcd_client import EtcdGatewayCoordinationClient
from distsys.coordination.models import CoordinationMember
from distsys.crdt_client import CrdtClient, RemoteCrdtError
from distsys.proto import messages_pb2


def is_transient_rejoin_error(code: int) -> bool:
    return code in {
        messages_pb2.RECOVERY_IN_PROGRESS,
        messages_pb2.CAUSAL_UNAVAILABLE,
    }


def parse_pid_file(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = int(value)
    return result


def replace_pid(path: Path, node_id: str, pid: int) -> None:
    pids = parse_pid_file(path)
    pids[node_id] = pid
    temp = path.with_suffix(".tmp")
    temp.write_text(
        "".join(f"{name}={value}\n" for name, value in sorted(pids.items())),
        encoding="utf-8",
    )
    temp.replace(path)


def read_durable_identity(db_path: Path) -> tuple[str, int, int]:
    with sqlite3.connect(db_path) as conn:
        identity = conn.execute(
            "SELECT node_uuid, causal_incarnation FROM node_identity WHERE singleton_id=1"
        ).fetchone()
        clock = conn.execute(
            "SELECT local_counter FROM causal_clock WHERE singleton_id=1"
        ).fetchone()
    if identity is None or clock is None:
        raise AssertionError("durable identity/clock missing")
    return str(identity[0]), int(identity[1]), int(clock[0])


def client_context(cert_dir: Path) -> ssl.SSLContext:
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


def node_env(root: Path, log_dir: Path, cert_dir: Path, node_id: str, port: int) -> dict[str, str]:
    env = os.environ.copy()
    old_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{root / 'src'}{os.pathsep}{old_pythonpath}" if old_pythonpath else str(root / "src")
    )
    env.update(
        {
            "NODE_ID": node_id,
            "NODE_HOST": "127.0.0.1",
            "NODE_PORT": str(port),
            "CPU_WORKERS": "1",
            "CPU_QUEUE_CAPACITY": "100",
            "RATE_LIMIT_RPS": "500",
            "RATE_LIMIT_BURST": "100",
            "REQUEST_TIMEOUT_SECONDS": "5",
            "CLUSTER_ENABLED": "true",
            "CLUSTER_SEEDS": "",
            "CLUSTER_VIRTUAL_NODES": "64",
            "CLUSTER_PROBE_INTERVAL_SECONDS": "0.5",
            "CLUSTER_PING_TIMEOUT_SECONDS": env.get("CLUSTER_PING_TIMEOUT_SECONDS", "0.75"),
            "CLUSTER_INDIRECT_TIMEOUT_SECONDS": env.get("CLUSTER_INDIRECT_TIMEOUT_SECONDS", "1.50"),
            "CLUSTER_INDIRECT_PROBE_COUNT": "2",
            "CLUSTER_SUSPICION_TIMEOUT_SECONDS": env.get(
                "CLUSTER_SUSPICION_TIMEOUT_SECONDS", "4.0"
            ),
            "CLUSTER_DEAD_RETENTION_SECONDS": "10",
            "CLUSTER_GOSSIP_INTERVAL_SECONDS": "0.5",
            "CRDT_ENABLED": "true",
            "CRDT_REPLICATION_FACTOR": "3",
            "CRDT_REPLICATION_QUEUE_CAPACITY": "500",
            "CRDT_REPLICATION_WORKERS": "1",
            "CRDT_REPLICATION_RETRY_MAX_ATTEMPTS": "3",
            "CRDT_REPLICATION_RETRY_BASE_DELAY_SECONDS": "0.05",
            "CRDT_REPLICATION_RETRY_MAX_DELAY_SECONDS": "0.5",
            "CRDT_ANTI_ENTROPY_INTERVAL_SECONDS": "1.0",
            "CRDT_ANTI_ENTROPY_BATCH_SIZE": "100",
            "PERSISTENCE_ENABLED": "true",
            "PERSISTENCE_DB_PATH": str(log_dir / "data" / f"{node_id}.db"),
            "PERSISTENCE_QUEUE_CAPACITY": "100",
            "PERSISTENCE_BUSY_TIMEOUT_SECONDS": "5",
            "PERSISTENCE_SQLITE_SYNCHRONOUS": "NORMAL",
            "ETCD_ENABLED": "true",
            "ETCD_ENDPOINTS": env.get("ETCD_ENDPOINTS", "http://127.0.0.1:2379"),
            "ETCD_NAMESPACE": env.get("ETCD_NAMESPACE", "/distsys/v1"),
            "ETCD_LEASE_TTL_SECONDS": env.get("ETCD_LEASE_TTL_SECONDS", "6"),
            "ETCD_RENEW_INTERVAL_SECONDS": env.get("ETCD_RENEW_INTERVAL_SECONDS", "2"),
            "TLS_ENABLED": "true",
            "MTLS_REQUIRED": "true",
            "TLS_CA_FILE": str(cert_dir / "ca" / "ca.crt"),
            "TLS_CERT_FILE": str(cert_dir / node_id / "node.crt"),
            "TLS_KEY_FILE": str(cert_dir / node_id / "node.key"),
            "TLS_MIN_VERSION": "TLSv1.3",
            "LOG_LEVEL": env.get("LOG_LEVEL", "INFO"),
        }
    )
    return env


async def discover_member(node_id: str) -> CoordinationMember | None:
    client = EtcdGatewayCoordinationClient(
        tuple(
            item.strip()
            for item in os.getenv("ETCD_ENDPOINTS", "http://127.0.0.1:2379").split(",")
            if item.strip()
        ),
        namespace=os.getenv("ETCD_NAMESPACE", "/distsys/v1"),
    )
    await client.connect()
    try:
        members = await client.discover_members()
        return next((item for item in members if item.node_id == node_id), None)
    finally:
        await client.close()


async def wait_member(node_id: str, *, present: bool, timeout: float) -> CoordinationMember | None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last = None
    while loop.time() < deadline:
        try:
            last = await discover_member(node_id)
        except (CoordinationUnavailableError, ConnectionError, OSError, TimeoutError):
            last = None
        if (last is not None) is present:
            return last
        await asyncio.sleep(0.25)
    raise TimeoutError(f"member {node_id} did not reach present={present}; last={last!r}")


async def main_async(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[1]
    log_dir = Path(args.log_dir).resolve()
    cert_dir = Path(args.cert_dir).resolve()
    pid_file = log_dir / "pids.env"
    pids = parse_pid_file(pid_file)
    if "node-2" not in pids:
        raise RuntimeError("node-2 PID is missing")

    db_path = log_dir / "data" / "node-2.db"
    node_uuid_before, causal_incarnation_before, counter_before = read_durable_identity(db_path)
    member_before = await wait_member("node-2", present=True, timeout=5)
    if member_before is None:
        raise AssertionError("node-2 disappeared before restart verification")
    old_swim_incarnation = int(member_before.membership_incarnation)

    tls = client_context(cert_dir)
    writer = CrdtClient(
        port=18000,
        timeout_seconds=5,
        ssl_context=tls,
        server_hostname="node-0",
    )
    key = f"phase5.restart.{time.time_ns()}"
    first = await writer.increment(key)

    # This is a crash-recovery test. SIGKILL guarantees the old process cannot
    # continue renewing its etcd lease while the test waits for lease expiry.
    os.kill(pids["node-2"], signal.SIGKILL)
    await wait_member("node-2", present=False, timeout=20)

    advanced = await writer.increment(key, amount=2, causal_token=first.causal_token)
    if advanced.value != 3:
        raise AssertionError("write during node-2 outage did not succeed")

    restart_log = (log_dir / "node-2-restarted.log").open("wb")
    try:
        restarted = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "distsys.main",
            cwd=str(root),
            env=node_env(root, log_dir, cert_dir, "node-2", 18002),
            stdout=restart_log,
            stderr=asyncio.subprocess.STDOUT,
        )
    finally:
        restart_log.close()
    replace_pid(pid_file, "node-2", restarted.pid)

    member_after = await wait_member("node-2", present=True, timeout=12)
    if member_after is None:
        raise AssertionError("node-2 disappeared after restart")
    if int(member_after.membership_incarnation) <= old_swim_incarnation:
        raise AssertionError("node-2 SWIM incarnation did not advance")

    reader = CrdtClient(
        port=18002,
        timeout_seconds=5,
        ssl_context=tls,
        server_hostname="node-2",
    )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 12
    value = None
    while loop.time() < deadline:
        try:
            value = await reader.read(key, causal_token=advanced.causal_token)
        except RemoteCrdtError as exc:
            if not is_transient_rejoin_error(exc.code):
                raise
            await asyncio.sleep(0.25)
            continue
        except (ConnectionError, OSError, TimeoutError):
            await asyncio.sleep(0.25)
            continue
        if value.value == 3:
            break
        await asyncio.sleep(0.25)
    if value is None or value.value != 3:
        raise AssertionError("restarted node did not reconcile durable state")

    node_uuid_after, causal_incarnation_after, counter_after = read_durable_identity(db_path)
    if node_uuid_after != node_uuid_before:
        raise AssertionError("durable node UUID changed across restart")
    if causal_incarnation_after != causal_incarnation_before:
        raise AssertionError("durable causal actor changed across restart")
    if counter_after < counter_before:
        raise AssertionError("durable causal counter regressed")

    print("phase5_restart_durable_state=PASS")
    print("phase5_restart_new_swim_epoch=PASS")
    print("phase5_restart_same_causal_actor=PASS")
    print("phase5_restart_reconciliation=PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", default=".phase5-logs")
    parser.add_argument("--cert-dir", default="certs/generated")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
