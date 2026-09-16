#!/usr/bin/env python3
"""Verify that a CRDT value survives a StatefulSet pod restart."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from verify_cluster import ROOT, PortForward, run, tls_context

from distsys.crdt_client import CrdtClient


async def verify(namespace: str, release: str, work_dir: Path) -> dict[str, object]:
    pod = f"{release}-distributed-system-2"
    key = f"phase7.persistence.{time.time_ns()}"
    async with PortForward(namespace, pod, ("18002:8000",)):
        client = CrdtClient(
            port=18002,
            client_id="phase7-client",
            timeout_seconds=5,
            ssl_context=tls_context(work_dir),
            server_hostname=pod,
        )
        written = await client.increment(key, amount=7)

    pvc = run(
        "kubectl",
        "-n",
        namespace,
        "get",
        "pod",
        pod,
        "-o",
        "jsonpath={.spec.volumes[?(@.name=='data')].persistentVolumeClaim.claimName}",
    )
    if not pvc:
        raise AssertionError("pod does not have a data PVC")
    run("kubectl", "-n", namespace, "delete", "pod", pod, "--wait=true", timeout=60)
    for _ in range(60):
        try:
            run("kubectl", "-n", namespace, "get", "pod", pod, timeout=5)
            break
        except RuntimeError:
            await asyncio.sleep(1)
    else:
        raise AssertionError("replacement pod did not appear within 60 seconds")
    run(
        "kubectl",
        "-n",
        namespace,
        "wait",
        f"pod/{pod}",
        "--for=condition=Ready",
        "--timeout=180s",
        timeout=190,
    )

    async with PortForward(namespace, pod, ("18002:8000",)):
        client = CrdtClient(
            port=18002,
            client_id="phase7-client",
            timeout_seconds=5,
            ssl_context=tls_context(work_dir),
            server_hostname=pod,
        )
        observed = await client.read(key, causal_token=written.causal_token)
    if observed.value != 7:
        raise AssertionError(f"persistent value mismatch: {observed.value!r}")

    return {
        "schema_version": 1,
        "persistence_restart": "pass",
        "causal_read_after_restart": "pass",
        "pvc_bound": True,
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
