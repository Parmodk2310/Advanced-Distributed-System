import asyncio

import pytest

from distsys.causal import CausalActor, VersionVector
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.crdt import CrdtType, GCounter
from distsys.protocol.message import Message, MessageType
from distsys.replication.codec import CrdtResponseData
from distsys.replication.peer_client import (
    AntiEntropyPeerAdapter,
    CausalRepairPeerAdapter,
    CrdtPeerClient,
    CrdtPeerProtocolError,
    ReplicationTransportAdapter,
)
from distsys.resilience.deadline import Deadline
from distsys.storage import CrdtStore, StoredCrdtEntry


def member() -> ClusterMember:
    return ClusterMember("node-1", "127.0.0.1", 18001, MemberStatus.ALIVE, 1)


def state() -> StoredCrdtEntry:
    actor = CausalActor("node-0", 1)
    vv = VersionVector({actor: 1})
    return StoredCrdtEntry("k", CrdtType.GCOUNTER, GCounter().increment(actor), vv, vv)


class LowLevel:
    def __init__(self):
        self.replications = []
        self.fetch_response = CrdtResponseData(success=True, peer_frontier=VersionVector())
        self.digests = []

    async def replicate(self, peer, state, *, timeout_seconds):
        self.replications.append((peer.node_id, state, timeout_seconds))

    async def fetch(self, peer, key, *, timeout_seconds):
        return self.fetch_response

    async def digest(self, peer, entries, *, batch_size, timeout_seconds):
        self.digests.append((peer.node_id, entries, batch_size, timeout_seconds))
        return ()


@pytest.mark.asyncio
async def test_replication_adapter_resolves_node_id():
    low = LowLevel()
    target = member()
    adapter = ReplicationTransportAdapter(
        low,
        lambda node_id: target if node_id == "node-1" else None,
        0.5,
    )
    await adapter.send_state("node-1", state())
    assert low.replications[0][0] == "node-1"


@pytest.mark.asyncio
async def test_causal_repair_adapter_returns_state_and_frontier():
    low = LowLevel()
    entry = state()
    actor = CausalActor("node-1", 1)
    frontier = VersionVector({actor: 4})
    low.fetch_response = CrdtResponseData(success=True, state=entry, peer_frontier=frontier)
    adapter = CausalRepairPeerAdapter(low, timeout_cap_seconds=0.5)
    result = await adapter.fetch_state(member(), "k", Deadline.after(1))
    assert result.entry == entry
    assert result.causal_frontier == frontier


@pytest.mark.asyncio
async def test_anti_entropy_metadata_uses_digest_not_full_state():
    low = LowLevel()
    store = CrdtStore()
    entry = state()
    await store.put_if_absent(entry)
    actor = CausalActor("node-1", 1)
    merged = entry.causal_context.merge(VersionVector({actor: 3}))
    adapter = AntiEntropyPeerAdapter(low, store, timeout_seconds=0.5)
    await adapter.send_metadata(member(), "k", merged)
    assert low.replications == []
    assert len(low.digests) == 1
    assert low.digests[0][1][0].causal_context == merged


def test_crdt_peer_client_accepts_tls_context():
    from distsys.replication.peer_client import CrdtPeerClient

    context = object()
    client = CrdtPeerClient(local_node_id="node-0", ssl_context=context)  # type: ignore[arg-type]
    assert client.ssl_context is context


@pytest.mark.asyncio
async def test_crdt_peer_client_normalizes_incomplete_response(monkeypatch):
    client = CrdtPeerClient(local_node_id="node-0")
    peer = member()

    class Reader:
        async def readexactly(self, size):
            raise asyncio.IncompleteReadError(b"", size)

    class Writer:
        def write(self, data):
            pass

        async def drain(self):
            pass

        def close(self):
            pass

        async def wait_closed(self):
            pass

    async def open_connection(*args, **kwargs):
        return Reader(), Writer()

    monkeypatch.setattr(asyncio, "open_connection", open_connection)
    request = Message.new_request(sender_id="node-0", msg_type=MessageType.CRDT_FETCH, payload=b"")
    with pytest.raises(CrdtPeerProtocolError):
        await client._exchange(peer, request, timeout_seconds=0.5)
