#!/usr/bin/env python3
"""Phase-3 cluster smoke checks with an optional managed failure/rejoin scenario."""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from distsys.client import DistributedClient
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.peer_client import PeerClient
from distsys.resilience.retry import RetryPolicy

NODE_IDS = ("node-0", "node-1", "node-2")
DEFAULT_PORTS = (18000, 18001, 18002)


def endpoint(node_id: str, host: str, port: int) -> ClusterMember:
    """Create an endpoint-only member used to address a peer control request."""
    return ClusterMember(
        node_id=node_id,
        host=host,
        port=port,
        status=MemberStatus.ALIVE,
        incarnation=1,
    )


def build_peer_client() -> PeerClient:
    return PeerClient(
        local_node_id="phase3-smoke",
        retry_policy=RetryPolicy(
            max_attempts=3,
            base_delay_seconds=0.05,
            max_delay_seconds=1.0,
        ),
        circuit_breaker_failure_threshold=5,
        circuit_breaker_recovery_seconds=10.0,
    )


def events(caplog) -> list[str]:
    recorded: list[str] = []

    for record in caplog.records:
        event = record.__dict__.get("event")
        if isinstance(event, str):
            recorded.append(event)

    return recorded


async def ping_snapshot(
    peer_client: PeerClient,
    peer: ClusterMember,
    *,
    timeout_seconds: float = 0.5,
) -> tuple[ClusterMember, ...]:
    ack = await peer_client.ping(peer, (), timeout_seconds=timeout_seconds)
    if not ack.success:
        raise AssertionError(f"PING to {peer.node_id} returned success=false")
    if ack.target_node_id != peer.node_id:
        raise AssertionError(
            f"PING target mismatch: expected {peer.node_id}, got {ack.target_node_id}"
        )
    return ack.gossip


def all_three_alive(snapshot: tuple[ClusterMember, ...]) -> bool:
    by_id = {member.node_id: member for member in snapshot}
    return all(
        node_id in by_id and by_id[node_id].status is MemberStatus.ALIVE for node_id in NODE_IDS
    )


async def wait_for_convergence(
    peer_client: PeerClient,
    peers: tuple[ClusterMember, ...],
    *,
    timeout_seconds: float = 12.0,
) -> dict[str, tuple[ClusterMember, ...]]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    last: dict[str, tuple[ClusterMember, ...]] = {}

    while loop.time() < deadline:
        success = True
        for peer in peers:
            try:
                snapshot = await ping_snapshot(peer_client, peer)
            except (ConnectionError, TimeoutError, OSError):
                success = False
                break
            last[peer.node_id] = snapshot
            if not all_three_alive(snapshot):
                success = False
        if success:
            return last
        await asyncio.sleep(0.20)

    details = {
        node_id: [(m.node_id, m.status.name, m.incarnation) for m in snapshot]
        for node_id, snapshot in last.items()
    }
    raise AssertionError(f"cluster did not converge to three ALIVE members: {details}")


def build_ring(snapshot: tuple[ClusterMember, ...]) -> ConsistentHashRing:
    ring = ConsistentHashRing(virtual_nodes=64)
    ring.rebuild(snapshot)
    return ring


def find_remote_key(ring: ConsistentHashRing, ingress_node_id: str) -> str:
    for index in range(100_000):
        key = f"phase3-smoke-{index}"
        if ring.owner(key).node_id != ingress_node_id:
            return key
    raise AssertionError("could not find a routing key owned by a remote node")


async def verify_routing(
    *,
    host: str,
    ports: tuple[int, ...],
    snapshot: tuple[ClusterMember, ...],
) -> tuple[str, str, set[str]]:
    ring = build_ring(snapshot)
    key = find_remote_key(ring, "node-0")
    expected_owner = ring.owner(key).node_id

    client = DistributedClient(host=host, port=ports[0], timeout_seconds=5.0)
    result = await client.request("cluster.whoami", {}, routing_key=key)
    actual_owner = result.get("node_id") if isinstance(result, dict) else None
    if actual_owner != expected_owner:
        raise AssertionError(
            f"routed execution mismatch: expected {expected_owner}, got {actual_owner}"
        )

    owners = {ring.owner(f"distribution-{index}").node_id for index in range(100)}
    if len(owners) < 2:
        raise AssertionError(f"100 sample keys mapped to fewer than two nodes: {owners}")

    return key, expected_owner, owners


async def inspect_cluster(host: str, ports: tuple[int, ...]) -> dict[str, object]:
    if len(ports) != 3:
        raise ValueError("Phase-3 smoke requires exactly three ports")

    peer_client = build_peer_client()
    peers = tuple(endpoint(node_id, host, port) for node_id, port in zip(NODE_IDS, ports))
    snapshots = await wait_for_convergence(peer_client, peers)
    key, owner, owners = await verify_routing(
        host=host,
        ports=ports,
        snapshot=snapshots["node-0"],
    )
    return {
        "peer_client": peer_client,
        "peers": peers,
        "snapshots": snapshots,
        "routing_key": key,
        "owner": owner,
        "owners": owners,
    }


def parse_pid_file(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = int(value.strip())
    return values


async def wait_for_member_status(
    peer_client: PeerClient,
    peer: ClusterMember,
    target_node_id: str,
    statuses: set[MemberStatus],
    *,
    timeout_seconds: float,
) -> ClusterMember:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    last: ClusterMember | None = None
    while loop.time() < deadline:
        snapshot = await ping_snapshot(peer_client, peer)
        by_id = {member.node_id: member for member in snapshot}
        current = by_id.get(target_node_id)
        if current is not None:
            last = current
            if current.status in statuses:
                return current
        await asyncio.sleep(0.20)
    raise AssertionError(
        f"{target_node_id} did not reach {[s.name for s in statuses]}; last={last}"
    )


def node_environment(root: Path, node_id: str, port: int, seeds: str) -> dict[str, str]:
    env = os.environ.copy()
    previous_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{root / 'src'}{os.pathsep}{previous_pythonpath}"
        if previous_pythonpath
        else str(root / "src")
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
            "LOG_LEVEL": "INFO",
        }
    )
    return env


async def managed_failure_rejoin(
    *,
    host: str,
    ports: tuple[int, ...],
    managed_command: str,
) -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="phase3-smoke-") as temp_dir:
        log_dir = Path(temp_dir)
        env = os.environ.copy()
        env["PHASE3_LOG_DIR"] = str(log_dir)
        previous_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{root / 'src'}{os.pathsep}{previous_pythonpath}"
            if previous_pythonpath
            else str(root / "src")
        )

        runner = await asyncio.to_thread(
            subprocess.Popen,
            shlex.split(managed_command),
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        restarted_node2: subprocess.Popen[str] | None = None
        try:
            pid_file = log_dir / "pids.env"
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline and not pid_file.exists():
                if runner.poll() is not None:
                    output = runner.stdout.read() if runner.stdout is not None else ""
                    raise RuntimeError(f"managed cluster runner exited early:\n{output}")
                await asyncio.sleep(0.10)
            if not pid_file.exists():
                raise TimeoutError("managed cluster runner did not create pids.env")

            state = await inspect_cluster(host, ports)
            snapshots = state["snapshots"]
            assert isinstance(snapshots, dict)
            initial_snapshot = snapshots["node-0"]
            initial_node2 = {member.node_id: member for member in initial_snapshot}["node-2"]
            initial_ring = build_ring(initial_snapshot)
            failover_key = next(
                f"managed-failover-{index}"
                for index in range(100_000)
                if initial_ring.owner(f"managed-failover-{index}").node_id == "node-2"
            )
            before_failure = await DistributedClient(host=host, port=ports[0]).request(
                "cluster.whoami",
                {},
                routing_key=failover_key,
            )
            if before_failure.get("node_id") != "node-2":
                raise AssertionError("managed failover key did not execute on node-2 before stop")

            pids = parse_pid_file(pid_file)
            node2_pid = pids.get("node-2")
            if node2_pid is None:
                raise AssertionError("runner PID file does not contain node-2")
            os.kill(node2_pid, signal.SIGTERM)

            peer_client = state["peer_client"]
            peers = state["peers"]
            assert isinstance(peer_client, PeerClient)
            assert isinstance(peers, tuple)
            await wait_for_member_status(
                peer_client,
                peers[0],
                "node-2",
                {MemberStatus.SUSPECT, MemberStatus.DEAD},
                timeout_seconds=8.0,
            )

            snapshot_after_failure = await ping_snapshot(peer_client, peers[0])
            ring = build_ring(snapshot_after_failure)
            result = await DistributedClient(host=host, port=ports[0]).request(
                "cluster.whoami",
                {},
                routing_key=failover_key,
            )
            if result.get("node_id") == "node-2":
                raise AssertionError("failed node-2 still owned routed work")
            if ring.owner(failover_key).node_id != result.get("node_id"):
                raise AssertionError("failover result does not match rebuilt ring owner")

            node2_log = (log_dir / "node-2-restarted.log").open("w", encoding="utf-8")
            restarted_node2 = await asyncio.to_thread(
                subprocess.Popen,
                [sys.executable, "-m", "distsys.main"],
                cwd=root,
                env=node_environment(
                    root,
                    "node-2",
                    ports[2],
                    f"{host}:{ports[0]}",
                ),
                stdout=node2_log,
                stderr=subprocess.STDOUT,
                text=True,
            )

            rejoined = await wait_for_member_status(
                peer_client,
                peers[0],
                "node-2",
                {MemberStatus.ALIVE},
                timeout_seconds=8.0,
            )
            if rejoined.incarnation <= initial_node2.incarnation:
                raise AssertionError("restarted node-2 did not rejoin with a newer incarnation")

            print("managed_failure_detection=PASS")
            print("managed_failover=PASS")
            print("managed_rejoin=PASS")
        finally:
            if restarted_node2 is not None and restarted_node2.poll() is None:
                restarted_node2.terminate()
                try:
                    restarted_node2.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    restarted_node2.kill()
                    restarted_node2.wait(timeout=5)
            if runner.poll() is None:
                runner.terminate()
                try:
                    runner.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    runner.kill()
                    runner.wait(timeout=5)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--ports", type=int, nargs=3, default=DEFAULT_PORTS)
    parser.add_argument(
        "--managed-command",
        default=None,
        help=(
            "Launch and manage a cluster command before running failure/rejoin checks, "
            "for example 'bash scripts/run_phase3_cluster.sh'."
        ),
    )
    args = parser.parse_args()
    ports = tuple(args.ports)

    if args.managed_command:
        await managed_failure_rejoin(
            host=args.host,
            ports=ports,
            managed_command=args.managed_command,
        )
        return

    state = await inspect_cluster(args.host, ports)
    snapshots = state["snapshots"]
    owners = state["owners"]
    assert isinstance(snapshots, dict)
    assert isinstance(owners, set)
    print("endpoints_reachable=3/3")
    print("membership_converged=3/3 ALIVE on every snapshot")
    print(f"routing_key={state['routing_key']}")
    print(f"calculated_owner={state['owner']}")
    print(f"sample_key_owners={','.join(sorted(owners))}")
    print("remote_routed_execution=PASS")
    print("phase3_smoke=PASS")


if __name__ == "__main__":
    asyncio.run(main())
