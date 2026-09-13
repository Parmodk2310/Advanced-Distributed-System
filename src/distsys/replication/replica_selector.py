"""Replica placement backed by the Phase-3 consistent-hash ring."""

from __future__ import annotations

from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember


class ReplicaSelector:
    def __init__(self, ring: ConsistentHashRing, replication_factor: int = 3) -> None:
        if replication_factor < 1:
            raise ValueError("replication_factor must be >= 1")
        self.ring = ring
        self.replication_factor = replication_factor

    def replicas(self, key: str) -> tuple[ClusterMember, ...]:
        return tuple(self.ring.candidates(key)[: self.replication_factor])

    def is_replica(self, node_id: str, key: str) -> bool:
        return any(member.node_id == node_id for member in self.replicas(key))

    def first_remote_replica(self, local_node_id: str, key: str) -> ClusterMember | None:
        return next(
            (member for member in self.replicas(key) if member.node_id != local_node_id),
            None,
        )
