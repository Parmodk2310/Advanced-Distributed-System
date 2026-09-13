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
        crdt_anti_entropy_interval_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_session_token_propagates_dependency_across_keys(unused_tcp_port_factory):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    nodes = [
        DistributedNode(settings(node_id="node-0", port=ports[0])),
        DistributedNode(
            settings(
                node_id="node-1",
                port=ports[1],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
        DistributedNode(
            settings(
                node_id="node-2",
                port=ports[2],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
    ]
    try:
        for node in nodes:
            await node.start()

        async def ready():
            for node in nodes:
                if node.cluster_service is None:
                    return False
                snap = await node.cluster_service.membership.snapshot()
                if len(snap) != 3 or any(m.status is not MemberStatus.ALIVE for m in snap):
                    return False
            return True

        await wait_until(ready)

        a = await CrdtClient(port=ports[0], timeout_seconds=2).write_register("A", "seen")
        b = await CrdtClient(port=ports[2], timeout_seconds=2).write_register(
            "B", "depends-on-A", causal_token=a.causal_token
        )
        assert b.causal_token.version.dominates(a.causal_token.version)
        assert nodes[2].crdt_service is not None
        b_entry = await nodes[2].crdt_service.store.get("B")
        assert b_entry is not None
        assert b_entry.causal_context.dominates(a.causal_token.version)
    finally:
        for node in reversed(nodes):
            await node.stop()


@pytest.mark.asyncio
async def test_local_frontier_allows_new_key_before_dependency_replication(
    unused_tcp_port_factory,
):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    nodes = [
        DistributedNode(settings(node_id="node-0", port=ports[0])),
        DistributedNode(
            settings(
                node_id="node-1",
                port=ports[1],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
        DistributedNode(
            settings(
                node_id="node-2",
                port=ports[2],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
    ]
    try:
        for node in nodes:
            await node.start()

        async def ready():
            for node in nodes:
                if node.cluster_service is None or node.crdt_service is None:
                    return False
                snap = await node.cluster_service.membership.snapshot()
                if len(snap) != 3 or any(m.status is not MemberStatus.ALIVE for m in snap):
                    return False
            return True

        await wait_until(ready)

        for node in nodes:
            assert node.crdt_service is not None
            await node.crdt_service.replication.stop()

        client = CrdtClient(port=ports[0], timeout_seconds=2)
        first = await client.increment("session.first", amount=1)
        second = await client.increment(
            "session.second",
            amount=1,
            causal_token=first.causal_token,
        )

        assert second.value == 1
        assert second.causal_token.version.dominates(first.causal_token.version)
    finally:
        for node in reversed(nodes):
            await node.stop()


@pytest.mark.asyncio
async def test_local_frontier_allows_new_mvregister_key_before_dependency_replication(
    unused_tcp_port_factory,
):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    nodes = [
        DistributedNode(settings(node_id="node-0", port=ports[0])),
        DistributedNode(
            settings(
                node_id="node-1",
                port=ports[1],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
        DistributedNode(
            settings(
                node_id="node-2",
                port=ports[2],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
    ]
    try:
        for node in nodes:
            await node.start()

        async def ready():
            for node in nodes:
                if node.cluster_service is None or node.crdt_service is None:
                    return False
                snap = await node.cluster_service.membership.snapshot()
                if len(snap) != 3 or any(m.status is not MemberStatus.ALIVE for m in snap):
                    return False
            return True

        await wait_until(ready)

        for node in nodes:
            assert node.crdt_service is not None
            await node.crdt_service.replication.stop()

        session = CrdtClient(port=ports[0], timeout_seconds=2)
        first = await session.increment("session.counter", amount=1)
        register = await session.write_register(
            "session.status",
            {"state": "secure"},
        )

        assert register.value == [{"state": "secure"}]
        assert register.causal_token.version.dominates(first.causal_token.version)
    finally:
        for node in reversed(nodes):
            await node.stop()
