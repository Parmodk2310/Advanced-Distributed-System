#!/usr/bin/env python3
"""Secure persistence smoke for a running Phase-5 three-node cluster."""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import ssl
import tempfile
import time
from pathlib import Path

from distsys.causal import CausalToken
from distsys.crdt import CrdtType
from distsys.crdt_client import CrdtClient, CrdtResult, RemoteCrdtError
from distsys.proto import messages_pb2
from distsys.protocol.framing import encode_frame
from distsys.protocol.message import Message


async def run_command(*args: str, cwd: Path | None = None) -> None:
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"command failed ({process.returncode}): {' '.join(args)}\n{detail}")


def tls_context(cert_dir: Path, identity: str) -> ssl.SSLContext:
    context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH,
        cafile=str(cert_dir / "ca" / "ca.crt"),
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(
        str(cert_dir / identity / "node.crt"),
        str(cert_dir / identity / "node.key"),
    )
    return context


def client(
    cert_dir: Path, port: int, *, identity: str = "crdt-client", client_id: str | None = None
) -> CrdtClient:
    return CrdtClient(
        host="127.0.0.1",
        port=port,
        timeout_seconds=5,
        client_id=client_id or identity,
        ssl_context=tls_context(cert_dir, identity),
        server_hostname=f"node-{port - 18000}",
    )


def verify_database(path: Path) -> None:
    if not path.exists():
        raise AssertionError(f"missing durable database: {path}")
    with sqlite3.connect(path) as conn:
        version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        identity = conn.execute(
            "SELECT node_uuid, causal_incarnation FROM node_identity"
        ).fetchone()
        if version != 1:
            raise AssertionError(f"expected schema version 1 in {path}, got {version}")
        if identity is None:
            raise AssertionError(f"missing durable node identity in {path}")


async def read_when_ready(
    reader: CrdtClient,
    key: str,
    *,
    causal_token: CausalToken,
    timeout_seconds: float = 20.0,
) -> CrdtResult:
    """Retry only transient startup failures while a secure node becomes ready."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        try:
            return await reader.read(key, causal_token=causal_token)
        except RemoteCrdtError as exc:
            if exc.code not in {
                messages_pb2.RECOVERY_IN_PROGRESS,
                messages_pb2.CAUSAL_UNAVAILABLE,
            }:
                raise
        except (ssl.SSLError, ConnectionError, OSError, asyncio.IncompleteReadError):
            pass

        if loop.time() >= deadline:
            raise TimeoutError(f"node did not become ready for secure read of {key!r}")
        await asyncio.sleep(0.1)


async def verify_positive_flow(cert_dir: Path, data_dir: Path, ports: tuple[int, int, int]) -> None:
    suffix = str(time.time_ns())
    writer = client(cert_dir, ports[0])
    views = await writer.increment(f"phase5.views.{suffix}", amount=2)
    remote = client(cert_dir, ports[2])
    read = await read_when_ready(
        remote,
        f"phase5.views.{suffix}",
        causal_token=views.causal_token,
    )
    if read.value != 2:
        raise AssertionError(f"expected remote GCounter 2, got {read.value!r}")

    pn = await writer.increment(
        f"phase5.balance.{suffix}",
        amount=7,
        crdt_type=CrdtType.PNCOUNTER,
    )
    pn = await writer.decrement(f"phase5.balance.{suffix}", amount=2, causal_token=pn.causal_token)
    if pn.value != 5:
        raise AssertionError(f"expected PNCounter 5, got {pn.value!r}")

    tags = await writer.add(f"phase5.tags.{suffix}", "python")
    tags = await writer.add(f"phase5.tags.{suffix}", "distributed", causal_token=tags.causal_token)
    tags = await writer.remove(f"phase5.tags.{suffix}", "python", causal_token=tags.causal_token)
    if tags.value != ["distributed"]:
        raise AssertionError(f"unexpected ORSet value {tags.value!r}")

    register = await writer.write_register(f"phase5.status.{suffix}", {"state": "secure"})
    if register.value != [{"state": "secure"}]:
        raise AssertionError(f"unexpected MVRegister value {register.value!r}")

    await asyncio.sleep(0.5)
    for node_id in ("node-0", "node-1", "node-2"):
        verify_database(data_dir / f"{node_id}.db")

    print("phase5_mtls_cluster=PASS")
    print("phase5_durable_crdts=PASS")
    print("phase5_schema_v1=PASS")


async def verify_negative_tls(cert_dir: Path, port: int) -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="phase5-wrong-ca-") as temp:
        wrong = Path(temp) / "certs"
        await run_command(
            "bash",
            str(root / "scripts/generate_dev_certs.sh"),
            str(wrong),
            cwd=root,
        )
        wrong_client = CrdtClient(
            port=port,
            timeout_seconds=2,
            ssl_context=tls_context(wrong, "crdt-client"),
            server_hostname="node-0",
        )
        try:
            await wrong_client.read("does-not-matter")
        except (ssl.SSLError, ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        else:
            raise AssertionError("unknown CA connection unexpectedly succeeded")
    print("phase5_unknown_ca_rejected=PASS")

    impersonator = CrdtClient(
        port=port,
        client_id="node-1",
        timeout_seconds=2,
        ssl_context=tls_context(cert_dir, "node-2"),
        server_hostname="node-0",
    )
    try:
        await impersonator.read("does-not-matter")
    except (ssl.SSLError, ConnectionError, OSError, asyncio.IncompleteReadError):
        pass
    else:
        raise AssertionError("wrong logical node identity unexpectedly succeeded")
    print("phase5_wrong_node_identity_rejected=PASS")

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(encode_frame(Message.new_request(sender_id="client", payload=b"")))
        await writer.drain()
        data = await asyncio.wait_for(reader.read(1), timeout=2)
        if data != b"":
            raise AssertionError("plaintext request received TLS application data")
    finally:
        writer.close()
        await writer.wait_closed()
    print("phase5_plaintext_rejected=PASS")


async def main_async(args: argparse.Namespace) -> None:
    cert_dir = Path(args.cert_dir).resolve()
    data_dir = Path(args.data_dir).resolve()
    ports = tuple(args.ports)
    await verify_positive_flow(cert_dir, data_dir, ports)
    await verify_negative_tls(cert_dir, ports[0])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert-dir", default="certs/generated")
    parser.add_argument("--data-dir", default=".phase5-logs/data")
    parser.add_argument("--ports", nargs=3, type=int, default=(18000, 18001, 18002))
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
