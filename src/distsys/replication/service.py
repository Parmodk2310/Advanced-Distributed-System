"""Lifecycle facade coordinating Phase-4 replication components."""

from __future__ import annotations

from typing import Any, cast

from distsys.causal import VersionVector
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.replication.anti_entropy import AntiEntropyPeer, AntiEntropyService, PeerProvider
from distsys.replication.causal_repair import (
    CausalRepairPeer,
    CausalRepairResult,
    CausalRepairService,
)
from distsys.replication.digest import CrdtDigestEntry
from distsys.replication.outbox import OutboxReservation, ReplicationOutbox
from distsys.replication.replica_selector import ReplicaSelector
from distsys.replication.replicator import ReplicationPeerTransport, Replicator
from distsys.resilience.deadline import Deadline
from distsys.resilience.retry import RetryPolicy
from distsys.storage import CrdtStore, StoredCrdtEntry


class ReplicationService:
    def __init__(
        self,
        *,
        local_node_id: str,
        store: CrdtStore,
        ring: ConsistentHashRing,
        replication_factor: int,
        peer: Any | None = None,
        replication_peer: ReplicationPeerTransport | None = None,
        repair_peer: CausalRepairPeer | None = None,
        anti_entropy_peer: AntiEntropyPeer | None = None,
        peer_provider: PeerProvider,
        queue_capacity: int = 500,
        worker_count: int = 2,
        retry_policy: RetryPolicy | None = None,
        anti_entropy_interval_seconds: float = 2.0,
        anti_entropy_batch_size: int = 100,
    ) -> None:
        self.local_node_id = local_node_id
        self.store = store
        self.selector = ReplicaSelector(ring, replication_factor)
        self.outbox = ReplicationOutbox(queue_capacity)
        replication_transport = replication_peer or cast(ReplicationPeerTransport, peer)
        repair_transport = repair_peer or cast(CausalRepairPeer, peer)
        anti_entropy_transport = anti_entropy_peer or cast(AntiEntropyPeer, peer)
        self.replicator = Replicator(
            self.outbox,
            replication_transport,
            worker_count=worker_count,
            retry_policy=retry_policy,
        )
        self.repair = CausalRepairService(
            local_node_id,
            store,
            self.selector,
            repair_transport,
        )
        self.anti_entropy = AntiEntropyService(
            local_node_id,
            store,
            self.selector,
            anti_entropy_transport,
            peer_provider=peer_provider,
            batch_size=anti_entropy_batch_size,
            interval_seconds=anti_entropy_interval_seconds,
        )
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self.replicator.start()
        await self.anti_entropy.start()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await self.anti_entropy.stop()
        await self.replicator.stop()
        self._started = False

    async def reserve_write(
        self,
        key: str,
        replica_ids: tuple[str, ...],
    ) -> OutboxReservation:
        pairs = tuple((node_id, key) for node_id in replica_ids if node_id != self.local_node_id)
        return await self.outbox.reserve(pairs)

    async def cancel_write(self, reservation: OutboxReservation) -> None:
        await self.outbox.cancel(reservation)

    async def publish_write(
        self,
        reservation: OutboxReservation,
        entry: StoredCrdtEntry,
    ) -> None:
        await self.outbox.publish(reservation, {entry.key: entry})

    async def merge_replica_state(self, entry: StoredCrdtEntry) -> StoredCrdtEntry:
        return await self.store.merge_entry(entry)

    async def ensure_causal(
        self,
        key: str,
        required: VersionVector,
        deadline: Deadline,
    ) -> CausalRepairResult:
        return await self.repair.ensure(key, required, deadline)

    async def merge_metadata(
        self,
        key: str,
        causal_context: VersionVector,
    ) -> StoredCrdtEntry | None:
        return await self.store.merge_metadata(key, causal_context)

    async def digest_snapshot(
        self,
        peer_node_id: str,
    ) -> tuple[CrdtDigestEntry, ...]:
        entries = await self.store.snapshot_all()
        relevant = []
        for entry in entries:
            ids = {member.node_id for member in self.selector.replicas(entry.key)}
            if self.local_node_id in ids and peer_node_id in ids:
                relevant.append(CrdtDigestEntry.from_entry(entry))
        return tuple(relevant)
