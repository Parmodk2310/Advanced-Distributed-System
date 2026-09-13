from dataclasses import replace

import pytest

from distsys.crdt_client import CrdtClient
from distsys.node import DistributedNode
from distsys.utils.config import Settings
from tests.integration.cluster_helpers import cluster_settings


def durable_settings(*, port: int, db_path: str) -> Settings:
    return replace(
        cluster_settings(node_id="node-0", port=port),
        crdt_enabled=True,
        crdt_replication_factor=1,
        persistence_enabled=True,
        persistence_db_path=db_path,
        etcd_enabled=False,
        tls_enabled=False,
    )


@pytest.mark.asyncio
async def test_node_restart_restores_crdt_and_durable_causal_actor(
    unused_tcp_port,
    tmp_path,
):
    db_path = str(tmp_path / "node-0.db")
    settings = durable_settings(port=unused_tcp_port, db_path=db_path)

    first = DistributedNode(settings)
    await first.start()
    try:
        assert first.cluster_service is not None
        assert first.crdt_service is not None
        first_swim_incarnation = first.cluster_service.local_member.incarnation
        first_actor = first.crdt_service.actor

        client = CrdtClient(port=unused_tcp_port, timeout_seconds=1.0)
        result = await client.increment("restart.counter")
        assert result.value == 1
        first_frontier = await first.crdt_service.clock.frontier()
        first_counter = first_frontier.get(first_actor)
        assert first_counter == 1
    finally:
        await first.stop()

    second = DistributedNode(settings)
    await second.start()
    try:
        assert second.cluster_service is not None
        assert second.crdt_service is not None
        assert second.cluster_service.local_member.incarnation != first_swim_incarnation
        assert second.crdt_service.actor == first_actor

        client = CrdtClient(port=unused_tcp_port, timeout_seconds=1.0)
        restored = await client.read("restart.counter")
        assert restored.value == 1

        advanced = await client.increment("restart.counter")
        assert advanced.value == 2
        second_frontier = await second.crdt_service.clock.frontier()
        assert second_frontier.get(first_actor) == first_counter + 1
    finally:
        await second.stop()
