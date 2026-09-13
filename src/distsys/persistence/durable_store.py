"""Persist-before-memory adapter for Phase-4 CRDT storage semantics."""

from __future__ import annotations

from distsys.causal import CausalClock, VersionVector
from distsys.crdt import CrdtType
from distsys.persistence.models import DurableCausalState
from distsys.persistence.repository import StateRepository
from distsys.resilience.deadline import Deadline
from distsys.storage import CrdtStore, StoredCrdtEntry
from distsys.storage.crdt_store import merge_entries


class DurableCrdtStore:
    def __init__(
        self,
        memory: CrdtStore,
        repository: StateRepository,
        clock: CausalClock,
    ) -> None:
        self.memory = memory
        self.repository = repository
        self.clock = clock

    def key_lock(self, key: str):
        return self.memory.key_lock(key)

    async def get(self, key: str) -> StoredCrdtEntry | None:
        return await self.memory.get(key)

    async def snapshot(self, key: str) -> StoredCrdtEntry | None:
        return await self.memory.snapshot(key)

    async def replace(
        self,
        entry: StoredCrdtEntry,
        expected_type: CrdtType | None = None,
    ) -> StoredCrdtEntry:
        return await self.memory.replace(entry, expected_type)

    async def keys(self) -> tuple[str, ...]:
        return await self.memory.keys()

    async def snapshot_all(self, limit: int | None = None) -> tuple[StoredCrdtEntry, ...]:
        return await self.memory.snapshot_all(limit)

    async def restore_entries(self, entries: tuple[StoredCrdtEntry, ...]) -> None:
        for entry in entries:
            await self.memory.replace(entry, expected_type=entry.crdt_type)

    async def commit_local(
        self,
        entry: StoredCrdtEntry,
        frontier: VersionVector,
        deadline: Deadline | None = None,
    ) -> StoredCrdtEntry:
        causal_state = DurableCausalState(
            actor=self.clock.actor,
            local_counter=frontier.get(self.clock.actor),
            frontier=frontier,
        )
        await self.repository.commit_mutation(entry, causal_state, deadline)
        return await self.memory.replace(entry, expected_type=entry.crdt_type)

    async def merge_entry(self, incoming: StoredCrdtEntry) -> StoredCrdtEntry:
        async with self.memory.key_lock(incoming.key):
            existing = await self.memory.get(incoming.key)
            merged = incoming if existing is None else merge_entries(existing, incoming)
            async with self.clock.staged_observe(merged.causal_context) as observation:
                causal_state = DurableCausalState(
                    actor=self.clock.actor,
                    local_counter=observation.frontier.get(self.clock.actor),
                    frontier=observation.frontier,
                )
                await self.repository.commit_observed_entry(merged, causal_state)
                result = await self.memory.replace(merged, expected_type=merged.crdt_type)
                observation.commit()
                return result

    async def merge_metadata(
        self,
        key: str,
        causal_context: VersionVector,
    ) -> StoredCrdtEntry | None:
        async with self.memory.key_lock(key):
            existing = await self.memory.get(key)
            if existing is None:
                return None
            updated = existing.with_context(existing.causal_context.merge(causal_context))
            async with self.clock.staged_observe(updated.causal_context) as observation:
                causal_state = DurableCausalState(
                    actor=self.clock.actor,
                    local_counter=observation.frontier.get(self.clock.actor),
                    frontier=observation.frontier,
                )
                await self.repository.commit_observed_entry(updated, causal_state)
                result = await self.memory.replace(updated, expected_type=existing.crdt_type)
                observation.commit()
                return result
