"""Lifecycle facade coordinating Phase-4 replication components."""

from __future__ import annotations

from typing import Any, cast

from distsys.causal import VersionVector
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember
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
from distsys.storage import StoredCrdtEntry
from distsys.storage.protocol import CrdtStateStore


class ReplicationService:
    def __init__(
        self,
        *,
        local_node_id: str,
        store: CrdtStateStore,
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
        self._replicator_started = False
        self._anti_entropy_started = False
        self.metrics: Any | None = None

    async def start_fast_path(self) -> None:
        if self._replicator_started:
            return
        await self.replicator.start()
        self._replicator_started = True

    async def start_anti_entropy(self) -> None:
        if self._anti_entropy_started:
            return
        await self.anti_entropy.start()
        self._anti_entropy_started = True

    async def start(self) -> None:
        await self.start_fast_path()
        await self.start_anti_entropy()

    async def stop(self) -> None:
        if self._anti_entropy_started:
            await self.anti_entropy.stop()
            self._anti_entropy_started = False
        if self._replicator_started:
            await self.replicator.stop()
            self._replicator_started = False

    async def reserve_write(
        self,
        key: str,
        replica_ids: tuple[str, ...],
    ) -> OutboxReservation:
        pairs = tuple((node_id, key) for node_id in replica_ids if node_id != self.local_node_id)
        reservation = await self.outbox.reserve(pairs)
        if self.metrics is not None:
            self.metrics.set_replication_queue_depth(await self.outbox.pending_count())
        return reservation

    async def cancel_write(self, reservation: OutboxReservation) -> None:
        await self.outbox.cancel(reservation)
        if self.metrics is not None:
            self.metrics.set_replication_queue_depth(await self.outbox.pending_count())

    async def publish_write(
        self,
        reservation: OutboxReservation,
        entry: StoredCrdtEntry,
    ) -> None:
        await self.outbox.publish(reservation, {entry.key: entry})
        if self.metrics is not None:
            self.metrics.set_replication_queue_depth(await self.outbox.pending_count())

    async def merge_replica_state(self, entry: StoredCrdtEntry) -> StoredCrdtEntry:
        return await self.store.merge_entry(entry)

    async def ensure_causal(
        self,
        key: str,
        required: VersionVector,
        deadline: Deadline,
    ) -> CausalRepairResult:
        try:
            result = await self.repair.ensure(key, required, deadline)
        except Exception:
            if self.metrics is not None:
                self.metrics.causal_repair("failure")
            raise
        if self.metrics is not None:
            self.metrics.causal_repair("success" if result.contacted_nodes else "skipped")
        return result

    async def merge_metadata(
        self,
        key: str,
        causal_context: VersionVector,
    ) -> StoredCrdtEntry | None:
        return await self.store.merge_metadata(key, causal_context)

    async def reconcile_peer(
        self,
        peer: ClusterMember,
        keys: tuple[str, ...] | None = None,
    ) -> object:
        try:
            result = await self.anti_entropy.reconcile_peer(peer, keys)
        except Exception:
            if self.metrics is not None:
                self.metrics.anti_entropy_repair("failure")
            raise
        if self.metrics is not None:
            self.metrics.anti_entropy_repair("success")
        return result

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
