from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from distsys.cluster.member import SeedAddress
from distsys.utils.config import Settings


async def wait_until(
    predicate: Callable[[], Awaitable[bool]],
    *,
    timeout_seconds: float = 3.0,
    interval_seconds: float = 0.02,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        if await predicate():
            return
        if loop.time() >= deadline:
            raise AssertionError("condition did not become true before timeout")
        await asyncio.sleep(interval_seconds)


def cluster_settings(
    *,
    node_id: str,
    port: int,
    seeds: tuple[SeedAddress, ...] = (),
    rate_limit_rps: float = 10_000.0,
    rate_limit_burst: int = 1_000,
) -> Settings:
    return Settings(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        cpu_workers=1,
        cpu_queue_capacity=100,
        rate_limit_rps=rate_limit_rps,
        rate_limit_burst=rate_limit_burst,
        request_timeout_seconds=2.0,
        cluster_enabled=True,
        cluster_seeds=seeds,
        cluster_virtual_nodes=32,
        cluster_probe_interval_seconds=0.05,
        cluster_ping_timeout_seconds=0.03,
        cluster_indirect_timeout_seconds=0.05,
        cluster_indirect_probe_count=2,
        cluster_suspicion_timeout_seconds=0.20,
        cluster_dead_retention_seconds=1.0,
        cluster_gossip_interval_seconds=0.05,
    )
