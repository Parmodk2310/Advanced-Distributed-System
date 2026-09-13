#!/usr/bin/env python3
"""Phase-4 causal CRDT smoke checks for a three-node local cluster."""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import signal
import sys
import tempfile
import time
from pathlib import Path

from phase3_smoke import (
    NODE_IDS,
    inspect_cluster,
    parse_pid_file,
    wait_for_member_status,
)

from distsys.cluster.member import MemberStatus
from distsys.crdt_client import CrdtClient

DEFAULT_PORTS = (18000, 18001, 18002)


async def verify_crdt_flow(host: str, ports: tuple[int, ...]) -> dict[str, object]:
    suffix = str(time.time_ns())
    writer = CrdtClient(host=host, port=ports[0], timeout_seconds=5)
    views = await writer.increment(f"phase4.views.{suffix}", amount=2)

    remote = CrdtClient(host=host, port=ports[2], timeout_seconds=5)
    read_views = await remote.read(
        f"phase4.views.{suffix}",
        causal_token=views.causal_token,
    )
    if read_views.value != 2:
        raise AssertionError(f"expected GCounter=2, got {read_views.value!r}")
    if not read_views.causal_token.version.dominates(views.causal_token.version):
        raise AssertionError("remote read did not preserve the writer causal token")

    tags = await writer.add(f"phase4.tags.{suffix}", "python")
    tags = await writer.add(
        f"phase4.tags.{suffix}",
        "distributed-systems",
        causal_token=tags.causal_token,
    )
    if tags.value != ["distributed-systems", "python"]:
        raise AssertionError(f"unexpected ORSet value: {tags.value!r}")

    status = await remote.write_register(
        f"phase4.status.{suffix}",
        {"risk": "medium"},
        causal_token=read_views.causal_token,
    )
    if status.value != [{"risk": "medium"}]:
        raise AssertionError(f"unexpected MVRegister value: {status.value!r}")

    return {
        "suffix": suffix,
        "views": views,
        "remote_read": read_views,
        "tags": tags,
        "status": status,
    }


def _node_env(
    root: Path,
    node_id: str,
    port: int,
    seeds: str,
    *,
    anti_entropy_interval_seconds: float = 2.0,
) -> dict[str, str]:
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
            "CLUSTER_SEEDS": seeds,
            "CLUSTER_VIRTUAL_NODES": "64",
            "CLUSTER_PROBE_INTERVAL_SECONDS": "1.0",
            "CLUSTER_PING_TIMEOUT_SECONDS": "0.25",
            "CLUSTER_INDIRECT_TIMEOUT_SECONDS": "0.50",
            "CLUSTER_INDIRECT_PROBE_COUNT": "2",
            "CLUSTER_SUSPICION_TIMEOUT_SECONDS": "3.0",
            "CLUSTER_DEAD_RETENTION_SECONDS": "30.0",
            "CLUSTER_GOSSIP_INTERVAL_SECONDS": "1.0",
            "CRDT_ENABLED": "true",
            "CRDT_REPLICATION_FACTOR": "3",
            "CRDT_REPLICATION_QUEUE_CAPACITY": "500",
            "CRDT_REPLICATION_WORKERS": "2",
            "CRDT_REPLICATION_RETRY_MAX_ATTEMPTS": "3",
            "CRDT_REPLICATION_RETRY_BASE_DELAY_SECONDS": "0.05",
            "CRDT_REPLICATION_RETRY_MAX_DELAY_SECONDS": "1.0",
            "CRDT_ANTI_ENTROPY_INTERVAL_SECONDS": str(anti_entropy_interval_seconds),
            "CRDT_ANTI_ENTROPY_BATCH_SIZE": "100",
            "LOG_LEVEL": "INFO",
        }
    )
    return env


async def managed_rejoin(*, host: str, ports: tuple[int, ...], managed_command: str) -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="phase4-smoke-") as temp_dir:
        log_dir = Path(temp_dir)
        env = os.environ.copy()
        env["PHASE4_LOG_DIR"] = str(log_dir)
        # Delay background anti-entropy so the rejoin read deterministically
        # demonstrates targeted causal repair instead of racing a repair loop.
        env["CRDT_ANTI_ENTROPY_INTERVAL_SECONDS"] = "30.0"
        old_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{root / 'src'}{os.pathsep}{old_pythonpath}" if old_pythonpath else str(root / "src")
        )
        runner = await asyncio.create_subprocess_exec(
            *shlex.split(managed_command),
            cwd=root,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        restarted: asyncio.subprocess.Process | None = None
        restart_log = None
        try:
            pid_file = log_dir / "pids.env"
            deadline = time.monotonic() + 12
            pids: dict[str, int] = {}
            while time.monotonic() < deadline:
                if runner.returncode is not None:
                    output = await runner.stdout.read() if runner.stdout else b""
                    raise RuntimeError(
                        "Phase-4 cluster exited early:\n" f"{output.decode(errors='replace')}"
                    )
                if pid_file.exists():
                    pids = parse_pid_file(pid_file)
                    if all(node_id in pids for node_id in NODE_IDS):
                        break
                await asyncio.sleep(0.1)
            if not all(node_id in pids for node_id in NODE_IDS):
                raise TimeoutError("Phase-4 cluster did not publish all node PIDs")

            cluster = await inspect_cluster(host, ports)
            flow = await verify_crdt_flow(host, ports)
            peer_client = cluster["peer_client"]
            peers = cluster["peers"]
            snapshots = cluster["snapshots"]
            initial = {m.node_id: m for m in snapshots["node-0"]}["node-2"]

            os.kill(pids["node-2"], signal.SIGTERM)
            await wait_for_member_status(
                peer_client,
                peers[0],
                "node-2",
                {MemberStatus.SUSPECT, MemberStatus.DEAD},
                timeout_seconds=9,
            )

            key = f"phase4.failure.views.{flow['suffix']}"
            writer = CrdtClient(host=host, port=ports[0], timeout_seconds=5)
            one = await writer.increment(key)
            two = await writer.increment(key, causal_token=one.causal_token)
            if two.value != 2:
                raise AssertionError("write with reduced effective RF did not succeed")

            restart_log = (log_dir / "node-2-restarted.log").open("w", encoding="utf-8")
            restarted = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "distsys.main",
                cwd=root,
                env=_node_env(
                    root,
                    "node-2",
                    ports[2],
                    f"{host}:{ports[0]}",
                    anti_entropy_interval_seconds=30.0,
                ),
                stdout=restart_log,
                stderr=asyncio.subprocess.STDOUT,
            )
            rejoined = await wait_for_member_status(
                peer_client,
                peers[0],
                "node-2",
                {MemberStatus.ALIVE},
                timeout_seconds=10,
            )
            if rejoined.incarnation <= initial.incarnation:
                raise AssertionError("rejoined node did not get a newer incarnation")

            deadline = time.monotonic() + 10
            recovered = False
            while time.monotonic() < deadline:
                try:
                    reader = CrdtClient(host=host, port=ports[2], timeout_seconds=2)
                    value = await reader.read(key, causal_token=two.causal_token)
                    if value.value == 2:
                        if not value.repair_performed:
                            raise AssertionError(
                                "rejoined stale replica did not perform targeted causal repair"
                            )
                        recovered = True
                        break
                except (ConnectionError, TimeoutError, OSError):
                    pass
                await asyncio.sleep(0.25)
            if not recovered:
                raise AssertionError("rejoined node did not recover CRDT state")

            print("phase4_managed_failure_detection=PASS")
            print("phase4_reduced_rf_write=PASS")
            print("phase4_rejoin_new_causal_epoch=PASS")
            print("phase4_rejoin_targeted_causal_repair=PASS")
            print("phase4_rejoin_recovery=PASS")
        finally:
            if restart_log is not None:
                restart_log.close()
            if restarted is not None and restarted.returncode is None:
                restarted.terminate()
                try:
                    await asyncio.wait_for(restarted.wait(), timeout=5)
                except TimeoutError:
                    restarted.kill()
                    await restarted.wait()
            if runner.returncode is None:
                runner.terminate()
                try:
                    await asyncio.wait_for(runner.wait(), timeout=8)
                except TimeoutError:
                    runner.kill()
                    await runner.wait()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--ports", type=int, nargs=3, default=DEFAULT_PORTS)
    parser.add_argument("--managed-command", default=None)
    args = parser.parse_args()
    ports = tuple(args.ports)

    if args.managed_command:
        await managed_rejoin(
            host=args.host,
            ports=ports,
            managed_command=args.managed_command,
        )
        return

    await inspect_cluster(args.host, ports)
    result = await verify_crdt_flow(args.host, ports)
    print("phase3_membership_converged=PASS")
    print("gcounter_remote_causal_read=PASS")
    print(f"causal_read_repair_performed={str(result['remote_read'].repair_performed).lower()}")
    print("orset_operations=PASS")
    print("mvregister_operation=PASS")
    print("phase4_smoke=PASS")


if __name__ == "__main__":
    asyncio.run(main())
