"""Recovery-time replica ownership and deterministic anti-entropy reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.replication.service import ReplicationService
from distsys.storage.protocol import CrdtStateStore


class AuthorityRepository(Protocol):
    async def mark_authority(self, key: str, authoritative: bool) -> None: ...


@dataclass(frozen=True, slots=True)
class RecoveryReconciliationResult:
    keys_checked: int
    authoritative_keys: int
    peers_contacted: int
    failures: int


class RecoveryReconciler:
    def __init__(
        self,
        local_node_id: str,
        store: CrdtStateStore,
        replication: ReplicationService,
        repository: AuthorityRepository,
    ) -> None:
        self.local_node_id = local_node_id
        self.store = store
        self.replication = replication
        self.repository = repository

    async def reconcile(
        self,
        peers: tuple[ClusterMember, ...],
    ) -> RecoveryReconciliationResult:
        keys = await self.store.keys()
        authoritative: list[str] = []
        replica_ids_by_key: dict[str, set[str]] = {}
        for key in keys:
            ids = {member.node_id for member in self.replication.selector.replicas(key)}
            replica_ids_by_key[key] = ids
            owned = self.local_node_id in ids
            await self.repository.mark_authority(key, owned)
            if owned:
                authoritative.append(key)

        contacted = 0
        failures = 0
        for peer in peers:
            if peer.node_id == self.local_node_id or peer.status is not MemberStatus.ALIVE:
                continue
            relevant = tuple(
                key for key in authoritative if peer.node_id in replica_ids_by_key[key]
            )
            if not relevant:
                continue
            contacted += 1
            try:
                stats = await self.replication.reconcile_peer(peer, relevant)
            except (ConnectionError, TimeoutError, OSError):
                failures += 1
                continue
            failures += getattr(stats, "failures", 0)

        return RecoveryReconciliationResult(
            keys_checked=len(keys),
            authoritative_keys=len(authoritative),
            peers_contacted=contacted,
            failures=failures,
        )
