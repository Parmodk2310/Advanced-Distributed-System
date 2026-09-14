#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import urllib.request


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.loads(response.read())


def get_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.read().decode()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ports", nargs="+", type=int, default=[9100, 9101, 9102])
    args = parser.parse_args()
    for port in args.ports:
        ready = await asyncio.to_thread(get_json, f"http://127.0.0.1:{port}/health/ready")
        if not ready["readiness"]:
            raise SystemExit(f"node on observability port {port} is not ready")
        text = await asyncio.to_thread(get_text, f"http://127.0.0.1:{port}/metrics")
        if "distsys_requests_total" not in text:
            raise SystemExit(f"missing Phase 6 metrics on {port}")
    print("Phase 6 observability smoke passed for", args.ports)


if __name__ == "__main__":
    asyncio.run(main())
