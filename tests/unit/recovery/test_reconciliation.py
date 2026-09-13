import pytest

from distsys.causal import CausalActor, VersionVector
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.crdt import CrdtType, GCounter
from distsys.recovery.reconciliation import RecoveryReconciler
from distsys.replication.service import ReplicationService
from distsys.resilience.retry import RetryPolicy
from distsys.storage import CrdtStore, StoredCrdtEntry


def member(node_id, port):
    return ClusterMember(node_id, "127.0.0.1", port, MemberStatus.ALIVE, 1)


class Repo:
    def __init__(self):
        self.authority = {}

    async def mark_authority(self, key, authoritative):
        self.authority[key] = authoritative


class Peer:
    async def send_state(self, *args, **kwargs):
        pass

    async def fetch_state(self, *args, **kwargs):
        if len(args) >= 3:
            from distsys.replication.causal_repair import PeerCrdtFetch

            return PeerCrdtFetch(args[0].node_id, None, VersionVector())
        return None

    async def exchange_digest(self, peer, digest_entries):
        return tuple(digest_entries)

    async def send_metadata(self, *args, **kwargs):
        pass


@pytest.mark.asyncio
async def test_reconciler_persists_current_authority():
    members = [member("node-0", 18000), member("node-1", 18001)]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(members)
    store = CrdtStore()
    actor = CausalActor("node-0", 1)
    vv = VersionVector({actor: 1})
    await store.replace(StoredCrdtEntry("k", CrdtType.GCOUNTER, GCounter({actor: 1}), vv, vv))
    repl = ReplicationService(
        local_node_id="node-0",
        store=store,
        ring=ring,
        replication_factor=2,
        peer=Peer(),
        peer_provider=lambda: tuple(members),
        queue_capacity=4,
        worker_count=1,
        retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, max_delay_seconds=0),
        anti_entropy_interval_seconds=60,
        anti_entropy_batch_size=10,
    )
    repo = Repo()
    result = await RecoveryReconciler("node-0", store, repl, repo).reconcile((members[1],))
    assert repo.authority["k"] is True
    assert result.keys_checked == 1
