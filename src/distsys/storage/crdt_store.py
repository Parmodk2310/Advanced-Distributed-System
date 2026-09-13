"""Atomic in-memory CRDT storage with per-key serialization."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from distsys.crdt import CrdtType, GCounter, MVRegister, ORSet, PNCounter
from distsys.storage.models import CrdtState, StoredCrdtEntry


def _merge_state(left: CrdtState, right: CrdtState) -> CrdtState:
    if type(left) is not type(right):
        raise TypeError("cannot merge different CRDT state types")
    if isinstance(left, GCounter) and isinstance(right, GCounter):
        return left.merge(right)
    if isinstance(left, PNCounter) and isinstance(right, PNCounter):
        return left.merge(right)
    if isinstance(left, ORSet) and isinstance(right, ORSet):
        return left.merge(right)
    if isinstance(left, MVRegister) and isinstance(right, MVRegister):
        return left.merge(right)
    raise TypeError("unsupported CRDT state type")


def merge_entries(left: StoredCrdtEntry, right: StoredCrdtEntry) -> StoredCrdtEntry:
    if left.key != right.key:
        raise ValueError("cannot merge entries with different keys")
    if left.crdt_type is not right.crdt_type:
        raise TypeError("cannot merge different CRDT types for one key")
    return StoredCrdtEntry(
        key=left.key,
        crdt_type=left.crdt_type,
        state=_merge_state(left.state, right.state),
        state_version=left.state_version.merge(right.state_version),
        causal_context=left.causal_context.merge(right.causal_context),
    )


class CrdtStore:
    def __init__(self) -> None:
        self._entries: dict[str, StoredCrdtEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()

    async def _lock_for(self, key: str) -> asyncio.Lock:
        async with self._meta_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    @asynccontextmanager
    async def key_lock(self, key: str) -> AsyncIterator[None]:
        lock = await self._lock_for(key)
        async with lock:
            yield

    async def get(self, key: str) -> StoredCrdtEntry | None:
        async with self._meta_lock:
            return self._entries.get(key)

    async def snapshot(self, key: str) -> StoredCrdtEntry | None:
        return await self.get(key)

    async def put_if_absent(self, entry: StoredCrdtEntry) -> StoredCrdtEntry:
        async with self.key_lock(entry.key), self._meta_lock:
            existing = self._entries.get(entry.key)
            if existing is None:
                self._entries[entry.key] = entry
                return entry
            if existing.crdt_type is not entry.crdt_type:
                raise TypeError("cannot change CRDT type for existing key")
            return existing

    async def replace(
        self,
        entry: StoredCrdtEntry,
        expected_type: CrdtType | None = None,
    ) -> StoredCrdtEntry:
        async with self._meta_lock:
            existing = self._entries.get(entry.key)
            if (
                expected_type is not None
                and existing is not None
                and existing.crdt_type is not expected_type
            ):
                raise TypeError("existing CRDT type does not match expected type")
            if existing is not None and existing.crdt_type is not entry.crdt_type:
                raise TypeError("cannot change CRDT type for existing key")
            self._entries[entry.key] = entry
            return entry

    async def merge_entry(self, incoming: StoredCrdtEntry) -> StoredCrdtEntry:
        async with self.key_lock(incoming.key):
            existing = await self.get(incoming.key)
            if existing is None:
                return await self.replace(incoming)
            merged = merge_entries(existing, incoming)
            return await self.replace(merged, expected_type=existing.crdt_type)

    async def merge_metadata(self, key: str, causal_context) -> StoredCrdtEntry | None:
        async with self.key_lock(key):
            existing = await self.get(key)
            if existing is None:
                return None
            updated = existing.with_context(existing.causal_context.merge(causal_context))
            return await self.replace(updated, expected_type=existing.crdt_type)

    async def keys(self) -> tuple[str, ...]:
        async with self._meta_lock:
            return tuple(sorted(self._entries))

    async def snapshot_all(self, limit: int | None = None) -> tuple[StoredCrdtEntry, ...]:
        async with self._meta_lock:
            entries = tuple(self._entries[key] for key in sorted(self._entries))
        if limit is None:
            return entries
        if limit < 0:
            raise ValueError("limit must be non-negative")
        return entries[:limit]
