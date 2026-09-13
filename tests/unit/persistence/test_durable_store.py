from __future__ import annotations

from dataclasses import dataclass

import pytest

from distsys.causal import CausalActor, CausalClock, VersionVector
from distsys.crdt import CrdtType, GCounter
from distsys.persistence.durable_store import DurableCrdtStore
from distsys.persistence.errors import PersistenceUnavailableError
from distsys.storage import CrdtStore, StoredCrdtEntry


@dataclass
class FakeRepository:
    events: list[str]
    fail: bool = False
    entries: list[StoredCrdtEntry] | None = None

    async def commit_observed_entry(self, entry, causal_state, deadline=None):
        self.events.append("persist")
        if self.fail:
            raise PersistenceUnavailableError("disk")
        self.entries = [entry]

    async def commit_mutation(self, entry, causal_state, deadline=None):
        self.events.append("persist")
        if self.fail:
            raise PersistenceUnavailableError("disk")
        self.entries = [entry]

    async def mark_authority(self, key, authoritative):
        pass


def entry(value: int) -> StoredCrdtEntry:
    actor = CausalActor("node-0", 500)
    return StoredCrdtEntry(
        "k",
        CrdtType.GCOUNTER,
        GCounter({actor: value}),
        VersionVector({actor: value}),
        VersionVector({actor: value}),
    )


@pytest.mark.asyncio
async def test_remote_merge_persists_before_memory_visibility(monkeypatch):
    events: list[str] = []
    memory = CrdtStore()
    original_replace = memory.replace

    async def replace(*args, **kwargs):
        events.append("memory")
        return await original_replace(*args, **kwargs)

    monkeypatch.setattr(memory, "replace", replace)
    actor = CausalActor("node-0", 500)
    store = DurableCrdtStore(memory, FakeRepository(events), CausalClock(actor))
    await store.merge_entry(entry(2))
    assert events == ["persist", "memory"]


@pytest.mark.asyncio
async def test_remote_merge_repository_failure_leaves_memory_unchanged():
    events: list[str] = []
    memory = CrdtStore()
    actor = CausalActor("node-0", 500)
    store = DurableCrdtStore(memory, FakeRepository(events, fail=True), CausalClock(actor))
    with pytest.raises(PersistenceUnavailableError):
        await store.merge_entry(entry(2))
    assert await memory.get("k") is None


@pytest.mark.asyncio
async def test_commit_local_persists_before_installing_memory(monkeypatch):
    events: list[str] = []
    memory = CrdtStore()
    original_replace = memory.replace

    async def replace(*args, **kwargs):
        events.append("memory")
        return await original_replace(*args, **kwargs)

    monkeypatch.setattr(memory, "replace", replace)
    actor = CausalActor("node-0", 500)
    clock = CausalClock(actor)
    store = DurableCrdtStore(memory, FakeRepository(events), clock)
    frontier = VersionVector({actor: 2})
    await store.commit_local(entry(2), frontier)
    assert events == ["persist", "memory"]
