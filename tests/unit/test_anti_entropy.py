import pytest

from distsys.causal import CausalActor, VersionVector
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.crdt import CrdtType, GCounter
from distsys.replication.anti_entropy import AntiEntropyService
from distsys.replication.digest import CrdtDigestEntry
from distsys.replication.replica_selector import ReplicaSelector
from distsys.storage import CrdtStore, StoredCrdtEntry


def member(node_id: str, port: int) -> ClusterMember:
    return ClusterMember(node_id, "127.0.0.1", port, MemberStatus.ALIVE, 1)


def entry(key: str, actor: CausalActor, value: int, sv_counter: int) -> StoredCrdtEntry:
    vv = VersionVector({actor: sv_counter})
    return StoredCrdtEntry(key, CrdtType.GCOUNTER, GCounter().increment(actor, value), vv, vv)


def setup_selector():
    members = [member("node-0", 18000), member("node-1", 18001), member("node-2", 18002)]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(members)
    return members, ReplicaSelector(ring, 3)


class FakePeer:
    def __init__(self, remote_digests=(), remote_states=None):
        self.remote_digests = tuple(remote_digests)
        self.remote_states = remote_states or {}
        self.exchanges = []
        self.fetches = []
        self.sent_states = []
        self.sent_metadata = []

    async def exchange_digest(self, peer, digest_entries):
        self.exchanges.append((peer.node_id, tuple(digest_entries)))
        return self.remote_digests

    async def fetch_state(self, peer, key):
        self.fetches.append((peer.node_id, key))
        return self.remote_states.get(key)

    async def send_state(self, peer, state):
        self.sent_states.append((peer.node_id, state))

    async def send_metadata(self, peer, key, causal_context):
        self.sent_metadata.append((peer.node_id, key, causal_context))


@pytest.mark.asyncio
async def test_equal_digest_skips_state_transfer():
    members, selector = setup_selector()
    actor = CausalActor("node-0", 1)
    local = entry("k", actor, 2, 2)
    store = CrdtStore()
    await store.put_if_absent(local)
    remote_digest = CrdtDigestEntry.from_entry(local)
    peer = FakePeer((remote_digest,))
    svc = AntiEntropyService(
        "node-0",
        store,
        selector,
        peer,
        peer_provider=lambda: (members[1], members[2]),
        peer_chooser=lambda peers: peers[0],
        batch_size=100,
        interval_seconds=2,
    )
    await svc.run_once()
    assert peer.fetches == []
    assert peer.sent_states == []


@pytest.mark.asyncio
async def test_remote_ahead_fetches_and_merges():
    members, selector = setup_selector()
    local_actor = CausalActor("node-0", 1)
    remote_actor = CausalActor("node-1", 1)
    store = CrdtStore()
    await store.put_if_absent(entry("k", local_actor, 2, 1))
    remote = entry("k", remote_actor, 5, 2)
    peer = FakePeer((CrdtDigestEntry.from_entry(remote),), {"k": remote})
    svc = AntiEntropyService(
        "node-0",
        store,
        selector,
        peer,
        peer_provider=lambda: (members[1],),
        peer_chooser=lambda peers: peers[0],
        batch_size=100,
        interval_seconds=2,
    )
    await svc.run_once()
    merged = await store.get("k")
    assert merged is not None
    assert merged.state.value() == 7  # type: ignore[union-attr]
    assert peer.fetches == [("node-1", "k")]


@pytest.mark.asyncio
async def test_local_ahead_repairs_peer():
    members, selector = setup_selector()
    actor = CausalActor("node-0", 1)
    local = entry("k", actor, 4, 4)
    remote_old = entry("k", actor, 2, 2)
    store = CrdtStore()
    await store.put_if_absent(local)
    peer = FakePeer((CrdtDigestEntry.from_entry(remote_old),))
    svc = AntiEntropyService(
        "node-0",
        store,
        selector,
        peer,
        peer_provider=lambda: (members[1],),
        peer_chooser=lambda peers: peers[0],
        batch_size=100,
        interval_seconds=2,
    )
    await svc.run_once()
    assert peer.sent_states == [("node-1", local)]


@pytest.mark.asyncio
async def test_concurrent_state_is_merged_then_repaired_back():
    members, selector = setup_selector()
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    local = entry("k", a, 3, 3)
    remote = entry("k", b, 4, 4)
    store = CrdtStore()
    await store.put_if_absent(local)
    peer = FakePeer((CrdtDigestEntry.from_entry(remote),), {"k": remote})
    svc = AntiEntropyService(
        "node-0",
        store,
        selector,
        peer,
        peer_provider=lambda: (members[1],),
        peer_chooser=lambda peers: peers[0],
        batch_size=100,
        interval_seconds=2,
    )
    await svc.run_once()
    merged = await store.get("k")
    assert merged is not None and merged.state.value() == 7  # type: ignore[union-attr]
    assert peer.sent_states[-1][1] == merged


@pytest.mark.asyncio
async def test_metadata_only_uses_metadata_message_not_full_state():
    members, selector = setup_selector()
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    sv = VersionVector({a: 1})
    local = StoredCrdtEntry("k", CrdtType.GCOUNTER, GCounter().increment(a, 1), sv, sv)
    remote_digest = CrdtDigestEntry("k", CrdtType.GCOUNTER, sv, sv.merge(VersionVector({b: 3})))
    store = CrdtStore()
    await store.put_if_absent(local)
    peer = FakePeer((remote_digest,))
    svc = AntiEntropyService(
        "node-0",
        store,
        selector,
        peer,
        peer_provider=lambda: (members[1],),
        peer_chooser=lambda peers: peers[0],
        batch_size=100,
        interval_seconds=2,
    )
    await svc.run_once()
    updated = await store.get("k")
    assert updated is not None and updated.causal_context.get(b) == 3
    assert peer.fetches == []
    assert len(peer.sent_metadata) == 1


@pytest.mark.asyncio
async def test_batch_size_limits_local_digest_entries():
    members, selector = setup_selector()
    a = CausalActor("node-0", 1)
    store = CrdtStore()
    await store.put_if_absent(entry("a", a, 1, 1))
    await store.put_if_absent(entry("b", a, 2, 2))
    peer = FakePeer(())
    svc = AntiEntropyService(
        "node-0",
        store,
        selector,
        peer,
        peer_provider=lambda: (members[1],),
        peer_chooser=lambda peers: peers[0],
        batch_size=1,
        interval_seconds=2,
    )
    await svc.run_once()
    assert len(peer.exchanges[0][1]) == 1
