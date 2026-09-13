from dataclasses import replace

import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.crdt_client import CrdtClient
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


def settings(*, node_id: str, port: int, seeds=()):
    return replace(
        cluster_settings(node_id=node_id, port=port, seeds=seeds),
        crdt_enabled=True,
        crdt_replication_factor=3,
        crdt_replication_workers=1,
        crdt_anti_entropy_interval_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_stale_writer_repairs_mvregister_before_causally_later_write(
    unused_tcp_port_factory,
):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    node0 = DistributedNode(settings(node_id="node-0", port=ports[0]))
    node1 = DistributedNode(
        settings(
            node_id="node-1",
            port=ports[1],
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        )
    )
    node2 = DistributedNode(
        settings(
            node_id="node-2",
            port=ports[2],
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        )
    )
    started = []
    try:
        await node0.start()
        started.append(node0)
        await node1.start()
        started.append(node1)

        async def two_ready() -> bool:
            for node in (node0, node1):
                assert node.cluster_service is not None
                if len(await node.cluster_service.membership.snapshot()) != 2:
                    return False
            return True

        await wait_until(two_ready)
        first = await CrdtClient(port=ports[0], timeout_seconds=2).write_register(
            "profile.status", {"risk": "medium"}
        )

        await node2.start()
        started.append(node2)

        async def three_ready() -> bool:
            for node in (node0, node1, node2):
                if node.cluster_service is None or node.crdt_service is None:
                    return False
                snapshot = await node.cluster_service.membership.snapshot()
                if len(snapshot) != 3 or any(m.status is not MemberStatus.ALIVE for m in snapshot):
                    return False
            return True

        await wait_until(three_ready)
        assert node2.crdt_service is not None
        assert await node2.crdt_service.store.get("profile.status") is None

        second = await CrdtClient(port=ports[2], timeout_seconds=2).write_register(
            "profile.status",
            {"risk": "high"},
            causal_token=first.causal_token,
        )
        assert second.repair_performed is True
        assert second.value == [{"risk": "high"}]
        assert second.causal_token.version.dominates(first.causal_token.version)
    finally:
        for node in reversed(started):
            await node.stop()
