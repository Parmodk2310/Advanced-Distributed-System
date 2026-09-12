#!/usr/bin/env python3
"""Small correctness smoke test for Phase-2 built-in tasks."""

from __future__ import annotations

import argparse
import asyncio

from distsys.client import DistributedClient


async def run(host: str, port: int) -> None:
    client = DistributedClient(host=host, port=port)
    checks = [
        ("echo", {"message": "phase-2"}),
        ("hash", {"data": "phase-2", "rounds": 1}),
        ("sort", {"values": [5, 2, 4, 1, 3]}),
        ("aggregate", {"values": [1, 2, 3, 4]}),
    ]

    for task_name, payload in checks:
        result = await client.request(task_name, payload)
        print(f"{task_name}: {result}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    asyncio.run(run(args.host, args.port))


if __name__ == "__main__":
    main()
