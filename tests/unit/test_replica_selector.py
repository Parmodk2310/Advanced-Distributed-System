from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.replication.replica_selector import ReplicaSelector


def member(node_id: str, port: int, status=MemberStatus.ALIVE) -> ClusterMember:
    return ClusterMember(node_id, "127.0.0.1", port, status, 1)


def test_replica_selector_reuses_ring_candidate_order():
    ring = ConsistentHashRing(virtual_nodes=16)
    members = [member("node-0", 18000), member("node-1", 18001), member("node-2", 18002)]
    ring.rebuild(members)
    selector = ReplicaSelector(ring, replication_factor=3)
    assert selector.replicas("customer-123") == tuple(ring.candidates("customer-123")[:3])


def test_replication_factor_contracts_to_alive_candidates():
    ring = ConsistentHashRing(virtual_nodes=16)
    members = [member("node-0", 18000), member("node-1", 18001)]
    ring.rebuild(members)
    selector = ReplicaSelector(ring, replication_factor=3)
    assert len(selector.replicas("k")) == 2


def test_is_replica_and_first_remote():
    ring = ConsistentHashRing(virtual_nodes=16)
    members = [member("node-0", 18000), member("node-1", 18001), member("node-2", 18002)]
    ring.rebuild(members)
    selector = ReplicaSelector(ring, replication_factor=2)
    replicas = selector.replicas("k")
    assert selector.is_replica(replicas[0].node_id, "k")
    assert selector.first_remote_replica(replicas[0].node_id, "k") == replicas[1]
