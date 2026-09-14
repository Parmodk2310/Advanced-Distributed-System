#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from distsys.chaos.controller import ChaosController
from distsys.chaos.model import ProbeState
from distsys.chaos.safety import ManagedManifest
from distsys.chaos.toxiproxy import ToxiproxyClient
from distsys.client import DistributedClient
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.peer_client import PeerClient
from distsys.resilience.retry import RetryPolicy
from distsys.security.tls_context import build_client_context
from distsys.utils.config import Settings

PROXY_MAP = "node-0=127.0.0.1:19100,node-1=127.0.0.1:19101,node-2=127.0.0.1:19102"


def health_json(port: int) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health/ready",
            timeout=0.75,
        ) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read())
        except Exception:  # noqa: BLE001
            return None
    except Exception:  # noqa: BLE001 - health probe must tolerate injected failures
        return None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=sorted(ChaosController.SCENARIOS))
    parser.add_argument(
        "--target",
        default="node-1",
        choices=["node-0", "node-1", "node-2"],
    )
    parser.add_argument("--manifest", default=".phase6-logs/manifest.json")
    parser.add_argument("--max-seconds", type=float, default=30.0)
    parser.add_argument("--cert-dir", type=Path, default=Path("certs/generated"))
    args = parser.parse_args()

    os.environ.setdefault("RUN_CHAOS_TESTS", "1")
    os.environ.setdefault("PHASE6_PEER_PROXY_MAP", PROXY_MAP)
    cert_dir = args.cert_dir.resolve()
    settings = Settings(
        tls_enabled=True,
        mtls_required=True,
        tls_ca_file=str(cert_dir / "ca" / "ca.crt"),
        tls_cert_file=str(cert_dir / "node-0" / "node.crt"),
        tls_key_file=str(cert_dir / "node-0" / "node.key"),
    )
    ssl_context = build_client_context(settings)
    peer = PeerClient(
        local_node_id="node-0",
        retry_policy=RetryPolicy(
            max_attempts=1,
            base_delay_seconds=0,
            max_delay_seconds=0,
        ),
        circuit_breaker_failure_threshold=2,
        circuit_breaker_recovery_seconds=0.5,
        ssl_context=ssl_context,
    )
    task_client = DistributedClient(
        host="127.0.0.1",
        port=18000,
        client_id="node-0",
        timeout_seconds=1.5,
        ssl_context=ssl_context,
        server_hostname="node-0",
    )
    target_index = int(args.target.rsplit("-", 1)[1])
    target_member = ClusterMember(
        node_id=args.target,
        host="127.0.0.1",
        port=18000 + target_index,
        status=MemberStatus.ALIVE,
        incarnation=1,
    )

    async def probe() -> ProbeState:
        health = await asyncio.gather(*(asyncio.to_thread(health_json, 9100 + i) for i in range(3)))
        ready_nodes = tuple(
            f"node-{i}"
            for i, snapshot in enumerate(health)
            if snapshot is not None and bool(snapshot.get("readiness"))
        )
        coordination = tuple(
            f"node-{i}"
            for i, snapshot in enumerate(health)
            if snapshot is not None and bool(snapshot.get("coordination"))
        )

        reachable = False
        latency: float | None = None
        started = time.perf_counter()
        try:
            ack = await peer.ping(target_member, (), timeout_seconds=0.9)
            reachable = bool(ack.success)
            latency = time.perf_counter() - started
        except Exception:  # noqa: BLE001 - reachability probe records any peer failure
            latency = None

        data_plane_ok = False
        try:
            result = await task_client.request("echo", {"phase6": "chaos"})
            data_plane_ok = result == {"phase6": "chaos"}
        except Exception:  # noqa: BLE001 - data-plane probe converts failure to state
            data_plane_ok = False
        return ProbeState(
            ready_nodes=ready_nodes,
            coordination_healthy_nodes=coordination,
            target_reachable=reachable,
            peer_latency_seconds=latency,
            data_plane_ok=data_plane_ok,
        )

    controller = ChaosController(
        ManagedManifest.load(Path(args.manifest)),
        ToxiproxyClient(),
        probe,
    )
    result = await controller.run(
        args.scenario,
        max_seconds=args.max_seconds,
        target=args.target,
    )
    print(result.to_json())
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
