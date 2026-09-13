import asyncio
from dataclasses import replace

import pytest

from distsys.crdt_client import CrdtClient, RemoteCrdtError
from distsys.node import DistributedNode
from distsys.proto import messages_pb2
from distsys.protocol.message import Message, MessageType
from distsys.recovery.coordinator import RecoveryCoordinator
from distsys.replication.codec import decode_crdt_response
from distsys.utils.config import Settings
from tests.integration.cluster_helpers import cluster_settings, wait_until


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
async def test_crdt_request_before_service_creation_reports_recovery_in_progress(tmp_path):
    node = DistributedNode(durable_settings(port=0, db_path=str(tmp_path / "node.db")))
    request = Message.new_request(
        sender_id="client",
        msg_type=MessageType.CRDT_READ_REQUEST,
        payload=b"",
    )
    try:
        response = await node._handle_crdt(request)
        decoded = decode_crdt_response(response.payload)
        assert decoded.error_code == messages_pb2.RECOVERY_IN_PROGRESS
    finally:
        await node.executor.close()


@pytest.mark.asyncio
async def test_crdt_mutation_is_gated_until_reconciliation_completes(
    unused_tcp_port,
    tmp_path,
    monkeypatch,
):
    entered = asyncio.Event()
    release = asyncio.Event()
    original = RecoveryCoordinator.reconcile

    async def blocked_reconcile(self, peers):
        entered.set()
        await release.wait()
        return await original(self, peers)

    monkeypatch.setattr(RecoveryCoordinator, "reconcile", blocked_reconcile)

    node = DistributedNode(
        durable_settings(port=unused_tcp_port, db_path=str(tmp_path / "node-0.db"))
    )
    start_task = asyncio.create_task(node.start())
    try:
        await asyncio.wait_for(entered.wait(), timeout=2.0)

        async def listener_bound() -> bool:
            return node._server is not None and node._server.is_serving()

        await wait_until(listener_bound, timeout_seconds=1.0)

        client = CrdtClient(port=unused_tcp_port, timeout_seconds=1.0)
        with pytest.raises(RemoteCrdtError) as exc:
            await client.increment("recovery.gate")
        assert exc.value.code == 14

        assert node.crdt_service is not None
        assert await node.crdt_service.store.get("recovery.gate") is None

        release.set()
        await asyncio.wait_for(start_task, timeout=2.0)

        result = await client.increment("recovery.gate")
        assert result.value == 1
    finally:
        release.set()
        if not start_task.done():
            await asyncio.gather(start_task, return_exceptions=True)
        await node.stop()
