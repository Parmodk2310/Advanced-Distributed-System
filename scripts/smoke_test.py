#!/usr/bin/env python3
"""Phase-1 reliability smoke test.

Persistent mode isolates request/framing reliability from TCP connection churn.
Churn mode intentionally opens a new TCP connection per request and should be
reported separately because it measures a different workload.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import statistics
import time

from distsys.client import DistributedClient


async def run(host: str, port: int, requests: int, mode: str) -> None:
    client = DistributedClient(host=host, port=port)
    latencies_ms: list[float] = []
    failure_types: Counter[str] = Counter()
    mismatches = 0

    if mode == "persistent":
        await client.connect()

    started = time.perf_counter()
    try:
        for index in range(requests):
            payload = {"sequence": index, "message": "hello"}
            request_started = time.perf_counter()
            try:
                if mode == "persistent":
                    result = await client.request_connected("echo", payload)
                else:
                    result = await client.request("echo", payload)
                if result != payload:
                    mismatches += 1
            except Exception as exc:  # diagnostic tool: classify, don't hide
                failure_types[type(exc).__name__] += 1
            latencies_ms.append((time.perf_counter() - request_started) * 1000)
    finally:
        if mode == "persistent":
            await client.close()

    elapsed = time.perf_counter() - started
    failures = sum(failure_types.values()) + mismatches
    sorted_latencies = sorted(latencies_ms)

    def percentile(p: float) -> float:
        if not sorted_latencies:
            return 0.0
        index = min(len(sorted_latencies) - 1, int((len(sorted_latencies) - 1) * p))
        return sorted_latencies[index]

    print(f"mode={mode}")
    print(f"requests={requests}")
    print(f"success={requests - failures}")
    print(f"failures={failures}")
    print(f"mismatches={mismatches}")
    print(f"elapsed_seconds={elapsed:.3f}")
    print(f"requests_per_second={requests / elapsed:.2f}")
    print(f"p50_ms={statistics.median(latencies_ms):.3f}")
    print(f"p95_ms={percentile(0.95):.3f}")
    print(f"p99_ms={percentile(0.99):.3f}")
    if failure_types:
        print("failure_types:")
        for name, count in failure_types.most_common():
            print(f"  {name}={count}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--requests", type=int, default=10000)
    parser.add_argument(
        "--mode",
        choices=("persistent", "churn"),
        default="persistent",
        help="persistent=reuse one TCP connection; churn=new connection per request",
    )
    args = parser.parse_args()
    asyncio.run(run(args.host, args.port, args.requests, args.mode))


if __name__ == "__main__":
    main()
