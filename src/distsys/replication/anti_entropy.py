"""Replica-aware digest-driven anti-entropy."""

from __future__ import annotations

import asyncio
import inspect
import logging
import random
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from distsys.causal import VersionVector
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.replication.digest import CrdtDigestEntry, DigestRelation, compare_digest
from distsys.replication.replica_selector import ReplicaSelector
from distsys.storage import CrdtStore, StoredCrdtEntry

logger = logging.getLogger("distsys.replication.anti_entropy")


class AntiEntropyPeer(Protocol):
    async def exchange_digest(
        self,
        peer: ClusterMember,
        digest_entries: tuple[CrdtDigestEntry, ...],
    ) -> tuple[CrdtDigestEntry, ...]: ...

    async def fetch_state(self, peer: ClusterMember, key: str) -> StoredCrdtEntry | None: ...

    async def send_state(self, peer: ClusterMember, state: StoredCrdtEntry) -> None: ...

    async def send_metadata(
        self,
        peer: ClusterMember,
        key: str,
        causal_context: VersionVector,
    ) -> None: ...


PeerProvider = Callable[[], tuple[ClusterMember, ...] | Awaitable[tuple[ClusterMember, ...]]]
PeerChooser = Callable[[Sequence[ClusterMember]], ClusterMember]


class AntiEntropyService:
    def __init__(
        self,
        local_node_id: str,
        store: CrdtStore,
        selector: ReplicaSelector,
        peer: AntiEntropyPeer,
        *,
        peer_provider: PeerProvider,
        peer_chooser: PeerChooser | None = None,
        batch_size: int = 100,
        interval_seconds: float = 2.0,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        self.local_node_id = local_node_id
        self.store = store
        self.selector = selector
        self.peer = peer
        self.peer_provider = peer_provider
        self.peer_chooser = peer_chooser or random.choice
        self.batch_size = batch_size
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def _peers(self) -> tuple[ClusterMember, ...]:
        value = self.peer_provider()
        if inspect.isawaitable(value):
            value = await value
        return tuple(
            member
            for member in value
            if member.node_id != self.local_node_id and member.status is MemberStatus.ALIVE
        )

    def _shared_replica(self, key: str, peer_node_id: str) -> bool:
        ids = {member.node_id for member in self.selector.replicas(key)}
        return self.local_node_id in ids and peer_node_id in ids

    async def _local_digest_for(self, peer_node_id: str) -> tuple[CrdtDigestEntry, ...]:
        entries = await self.store.snapshot_all()
        relevant = [
            CrdtDigestEntry.from_entry(entry)
            for entry in entries
            if self._shared_replica(entry.key, peer_node_id)
        ]
        return tuple(relevant[: self.batch_size])

    async def run_once(self) -> None:
        peers = await self._peers()
        if not peers:
            return
        target = self.peer_chooser(peers)
        local_digest = await self._local_digest_for(target.node_id)
        try:
            remote_digest = await self.peer.exchange_digest(target, local_digest)
        except (ConnectionError, TimeoutError, OSError):
            logger.debug(
                "anti entropy digest failed",
                extra={"event": "anti_entropy_digest_failed", "peer_id": target.node_id},
            )
            return

        local_map = {item.key: item for item in local_digest}
        remote_map = {
            item.key: item
            for item in remote_digest
            if self._shared_replica(item.key, target.node_id)
        }

        for key in sorted(set(local_map) | set(remote_map))[: self.batch_size]:
            local = local_map.get(key)
            remote = remote_map.get(key)
            if local is None and remote is not None:
                state = await self.peer.fetch_state(target, key)
                if state is not None:
                    await self.store.merge_entry(state)
                continue
            if local is not None and remote is None:
                state = await self.store.get(key)
                if state is not None:
                    await self.peer.send_state(target, state)
                continue
            assert local is not None and remote is not None
            relation = compare_digest(local, remote)
            if relation is DigestRelation.EQUAL:
                continue
            if relation is DigestRelation.METADATA_ONLY:
                merged_context = local.causal_context.merge(remote.causal_context)
                await self.store.merge_metadata(key, merged_context)
                await self.peer.send_metadata(target, key, merged_context)
                continue
            if relation is DigestRelation.LOCAL_AHEAD:
                state = await self.store.get(key)
                if state is not None:
                    await self.peer.send_state(target, state)
                continue
            if relation is DigestRelation.REMOTE_AHEAD:
                state = await self.peer.fetch_state(target, key)
                if state is not None:
                    await self.store.merge_entry(state)
                continue
            if relation is DigestRelation.CONCURRENT:
                state = await self.peer.fetch_state(target, key)
                if state is None:
                    continue
                merged = await self.store.merge_entry(state)
                await self.peer.send_state(target, merged)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="crdt-anti-entropy")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("anti entropy iteration failed")
