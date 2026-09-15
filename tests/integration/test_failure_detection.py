import asyncio

import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_stopped_node_transitions_to_suspect_then_dead(unused_tcp_port_factory):
    p0, p1 = [unused_tcp_port_factory() for _ in range(2)]
    node0 = DistributedNode(cluster_settings(node_id="node-0", port=p0))
    node1 = DistributedNode(
        cluster_settings(
            node_id="node-1",
            port=p1,
            seeds=(SeedAddress("127.0.0.1", p0),),
        )
    )
    stop_task: asyncio.Task[None] | None = None
    try:
        await node0.start()
        await node1.start()

        service = node0.cluster_service
        assert service is not None

        async def joined() -> bool:
            return await service.membership.get("node-1") is not None

        await wait_until(joined)
        stop_task = asyncio.create_task(node1.stop())

        async def not_alive() -> bool:
            current = await service.membership.get("node-1")
            return current is None or current.status in {
                MemberStatus.SUSPECT,
                MemberStatus.DEAD,
            }

        await wait_until(not_alive, timeout_seconds=5.0)

        assert all(
            member.node_id != "node-1"
            for member in service.ring.candidates("any-key")
        )

        await stop_task

        async def dead_or_removed() -> bool:
            await service.membership.advance_timeouts_and_purge()
            current = await service.membership.get("node-1")
            return current is None or current.status is MemberStatus.DEAD

        await wait_until(dead_or_removed, timeout_seconds=5.0)
    finally:
        if stop_task is not None:
            await asyncio.gather(stop_task, return_exceptions=True)
        await node1.stop()
        await node0.stop()
