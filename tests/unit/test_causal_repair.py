import asyncio

import pytest

from distsys.causal import CausalActor, VersionVector
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.crdt import CrdtType, GCounter
from distsys.replication.causal_repair import (
    CausalRepairService,
    CausalUnavailableError,
    PeerCrdtFetch,
)
from distsys.replication.replica_selector import ReplicaSelector
from distsys.resilience.deadline import Deadline
from distsys.storage import CrdtStore, StoredCrdtEntry


def member(node_id: str, port: int) -> ClusterMember:
    return ClusterMember(node_id, "127.0.0.1", port, MemberStatus.ALIVE, 1)


def selector() -> ReplicaSelector:
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild([member("node-0", 18000), member("node-1", 18001), member("node-2", 18002)])
    return ReplicaSelector(ring, 3)


def state_for(key: str, actor: CausalActor, counter: int) -> StoredCrdtEntry:
    vv = VersionVector({actor: counter})
    return StoredCrdtEntry(key, CrdtType.GCOUNTER, GCounter().increment(actor, counter), vv, vv)


class FakePeer:
    def __init__(self, responses: dict[str, PeerCrdtFetch]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, Deadline]] = []

    async def fetch_state(self, peer, key: str, deadline: Deadline) -> PeerCrdtFetch:
        self.calls.append((peer.node_id, deadline))
        return self.responses[peer.node_id]


@pytest.mark.asyncio
async def test_local_fast_path_contacts_no_peer():
    actor = CausalActor("node-0", 1)
    store = CrdtStore()
    await store.put_if_absent(state_for("k", actor, 3))
    peer = FakePeer({})
    service = CausalRepairService("node-0", store, selector(), peer)
    deadline = Deadline.after(1)
    result = await service.ensure("k", VersionVector({actor: 2}), deadline)
    assert result.satisfied
    assert result.contacted_nodes == ()
    assert peer.calls == []


@pytest.mark.asyncio
async def test_parallel_peer_fetch_and_merge_satisfies_required_frontier():
    remote = CausalActor("node-1", 1)
    entered: set[str] = set()
    both_entered = asyncio.Event()
    release = asyncio.Event()

    class ParallelPeer:
        async def fetch_state(self, peer, key: str, deadline: Deadline) -> PeerCrdtFetch:
            entered.add(peer.node_id)
            if len(entered) >= 2:
                both_entered.set()
            await release.wait()
            if peer.node_id == "node-1":
                entry = state_for("k", remote, 8)
                return PeerCrdtFetch(peer.node_id, entry, VersionVector({remote: 8}))
            return PeerCrdtFetch(peer.node_id, None, VersionVector())

    store = CrdtStore()
    service = CausalRepairService("node-0", store, selector(), ParallelPeer())
    deadline = Deadline.after(1)
    task = asyncio.create_task(service.ensure("k", VersionVector({remote: 8}), deadline))
    await asyncio.wait_for(both_entered.wait(), timeout=0.5)
    release.set()
    result = await task
    assert result.satisfied
    assert result.merged_version.dominates(VersionVector({remote: 8}))
    assert len(result.contacted_nodes) == 2
    repaired = await store.get("k")
    assert repaired is not None
    assert repaired.causal_context.dominates(VersionVector({remote: 8}))


@pytest.mark.asyncio
async def test_unsatisfied_frontier_raises_causal_unavailable():
    remote = CausalActor("node-1", 1)
    responses = {
        "node-1": PeerCrdtFetch("node-1", None, VersionVector({remote: 6})),
        "node-2": PeerCrdtFetch("node-2", None, VersionVector({remote: 7})),
    }
    service = CausalRepairService("node-0", CrdtStore(), selector(), FakePeer(responses))
    with pytest.raises(CausalUnavailableError):
        await service.ensure("k", VersionVector({remote: 8}), Deadline.after(1))
