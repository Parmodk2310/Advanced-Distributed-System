import asyncio

import pytest

from distsys.causal import CausalActor, Dot, VersionVector
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.crdt import CrdtType, GCounter
from distsys.replication.service import ReplicationService
from distsys.resilience.retry import RetryPolicy
from distsys.storage import CrdtStore, StoredCrdtEntry


def member(node_id: str, port: int) -> ClusterMember:
    return ClusterMember(node_id, "127.0.0.1", port, MemberStatus.ALIVE, 1)


def state() -> StoredCrdtEntry:
    actor = CausalActor("node-0", 1)
    vv = VersionVector().with_dot(Dot(actor, 1))
    return StoredCrdtEntry("k", CrdtType.GCOUNTER, GCounter().increment(actor), vv, vv)


class Peer:
    def __init__(self):
        self.sent = asyncio.Event()

    async def send_state(self, peer_or_id, state):
        self.sent.set()

    async def fetch_state(self, peer, key, deadline=None):
        from distsys.replication.causal_repair import PeerCrdtFetch

        if deadline is None:
            return None
        return PeerCrdtFetch(peer.node_id, None, VersionVector())

    async def exchange_digest(self, peer, digest_entries):
        return ()

    async def send_metadata(self, peer, key, causal_context):
        return None


@pytest.mark.asyncio
async def test_service_reserve_publish_and_lifecycle():
    members = [member("node-0", 18000), member("node-1", 18001)]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(members)
    peer = Peer()
    store = CrdtStore()
    service = ReplicationService(
        local_node_id="node-0",
        store=store,
        ring=ring,
        replication_factor=2,
        peer=peer,
        peer_provider=lambda: tuple(members),
        queue_capacity=4,
        worker_count=1,
        retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0),
        anti_entropy_interval_seconds=60,
        anti_entropy_batch_size=10,
    )
    await service.start()
    reservation = await service.reserve_write("k", ("node-1",))
    await service.publish_write(reservation, state())
    await asyncio.wait_for(peer.sent.wait(), timeout=0.5)
    await service.stop()


@pytest.mark.asyncio
async def test_service_merge_replica_state_and_metadata():
    members = [member("node-0", 18000), member("node-1", 18001)]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(members)
    peer = Peer()
    service = ReplicationService(
        local_node_id="node-0",
        store=CrdtStore(),
        ring=ring,
        replication_factor=2,
        peer=peer,
        peer_provider=lambda: tuple(members),
        queue_capacity=4,
        worker_count=1,
        retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0),
        anti_entropy_interval_seconds=60,
        anti_entropy_batch_size=10,
    )
    merged = await service.merge_replica_state(state())
    assert merged.key == "k"
    actor = CausalActor("node-1", 1)
    updated = await service.merge_metadata("k", VersionVector({actor: 2}))
    assert updated is not None and updated.causal_context.get(actor) == 2
