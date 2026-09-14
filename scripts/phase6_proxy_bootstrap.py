#!/usr/bin/env python3
from __future__ import annotations

import asyncio

from distsys.chaos.toxiproxy import ToxiproxyClient

PROXIES = {
    "etcd": ("0.0.0.0:12379", "etcd:2379"),
    "peer-node-0": ("0.0.0.0:19100", "host.docker.internal:18000"),
    "peer-node-1": ("0.0.0.0:19101", "host.docker.internal:18001"),
    "peer-node-2": ("0.0.0.0:19102", "host.docker.internal:18002"),
}


async def main() -> None:
    client = ToxiproxyClient()
    existing = await client.proxies()
    for name, (listen, upstream) in PROXIES.items():
        if name in existing:
            await client.delete_proxy(name)
        await client.create_proxy(name, listen, upstream)
    print("Phase 6 Toxiproxy paths ready:", ", ".join(sorted(PROXIES)))


if __name__ == "__main__":
    asyncio.run(main())
