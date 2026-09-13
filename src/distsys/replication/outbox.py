"""Bounded coalescing CRDT replication outbox."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from distsys.storage import StoredCrdtEntry

Pair = tuple[str, str]


class ReplicationBackpressureError(RuntimeError):
    """Raised before mutation when the outbox cannot reserve required work."""


@dataclass(frozen=True, slots=True)
class OutboxReservation:
    pairs: tuple[Pair, ...]
    created_pairs: tuple[Pair, ...]


@dataclass(frozen=True, slots=True)
class PendingReplication:
    peer_node_id: str
    key: str
    generation: int
    state: StoredCrdtEntry


@dataclass(slots=True)
class _Pending:
    generation: int = 0
    state: StoredCrdtEntry | None = None
    queued: bool = False
    in_flight: bool = False


class ReplicationOutbox:
    def __init__(self, capacity: int = 500) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._pending: dict[Pair, _Pending] = {}
        self._ready: asyncio.Queue[Pair] = asyncio.Queue()
        self._lock = asyncio.Lock()

    async def reserve(self, pairs: tuple[Pair, ...]) -> OutboxReservation:
        unique = tuple(dict.fromkeys(pairs))
        async with self._lock:
            new_pairs = tuple(pair for pair in unique if pair not in self._pending)
            if len(self._pending) + len(new_pairs) > self.capacity:
                raise ReplicationBackpressureError("replication outbox capacity exhausted")
            for pair in new_pairs:
                self._pending[pair] = _Pending()
            return OutboxReservation(unique, new_pairs)

    async def cancel(self, reservation: OutboxReservation) -> None:
        async with self._lock:
            for pair in reservation.created_pairs:
                current = self._pending.get(pair)
                if current is not None and current.generation == 0 and current.state is None:
                    self._pending.pop(pair, None)

    async def publish(
        self,
        reservation: OutboxReservation,
        states_by_key: dict[str, StoredCrdtEntry],
    ) -> None:
        to_queue: list[Pair] = []
        async with self._lock:
            for pair in reservation.pairs:
                peer_node_id, key = pair
                _ = peer_node_id
                state = states_by_key.get(key)
                if state is None:
                    raise KeyError(f"missing published state for key {key!r}")
                current = self._pending.get(pair)
                if current is None:
                    raise RuntimeError("outbox reservation no longer exists")
                current.generation += 1
                current.state = state
                if not current.queued and not current.in_flight:
                    current.queued = True
                    to_queue.append(pair)
        for pair in to_queue:
            self._ready.put_nowait(pair)

    async def next_ready(self) -> PendingReplication:
        while True:
            pair = await self._ready.get()
            async with self._lock:
                current = self._pending.get(pair)
                if current is None or current.state is None or current.in_flight:
                    continue
                current.queued = False
                current.in_flight = True
                peer_node_id, key = pair
                return PendingReplication(
                    peer_node_id=peer_node_id,
                    key=key,
                    generation=current.generation,
                    state=current.state,
                )

    async def complete(self, peer_node_id: str, key: str, sent_generation: int) -> None:
        pair = (peer_node_id, key)
        requeue = False
        async with self._lock:
            current = self._pending.get(pair)
            if current is None:
                return
            current.in_flight = False
            if current.generation == sent_generation:
                self._pending.pop(pair, None)
            elif not current.queued:
                current.queued = True
                requeue = True
        if requeue:
            self._ready.put_nowait(pair)

    async def abandon(self, peer_node_id: str, key: str, sent_generation: int) -> None:
        pair = (peer_node_id, key)
        requeue = False
        async with self._lock:
            current = self._pending.get(pair)
            if current is None:
                return
            current.in_flight = False
            if current.generation == sent_generation:
                self._pending.pop(pair, None)
            elif not current.queued:
                current.queued = True
                requeue = True
        if requeue:
            self._ready.put_nowait(pair)

    async def pending_count(self) -> int:
        async with self._lock:
            return len(self._pending)
