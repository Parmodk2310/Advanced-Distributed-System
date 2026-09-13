import asyncio

import pytest

from distsys.causal import CausalActor, Dot, VersionVector
from distsys.crdt import CrdtType, GCounter, MVRegister
from distsys.storage import CrdtStore, StoredCrdtEntry


def make_counter_entry(key: str, value: int, counter: int = 1) -> StoredCrdtEntry:
    actor = CausalActor("node-0", 1)
    state = GCounter().increment(actor, value)
    vv = VersionVector().with_dot(Dot(actor, counter))
    return StoredCrdtEntry(
        key=key,
        crdt_type=CrdtType.GCOUNTER,
        state=state,
        state_version=vv,
        causal_context=vv,
    )


def test_entry_rejects_empty_key_and_type_mismatch():
    actor = CausalActor("node-0", 1)
    vv = VersionVector().with_dot(Dot(actor, 1))
    with pytest.raises(ValueError):
        StoredCrdtEntry("", CrdtType.GCOUNTER, GCounter(), vv, vv)
    with pytest.raises(TypeError):
        StoredCrdtEntry(
            "k",
            CrdtType.GCOUNTER,
            MVRegister().write("x", Dot(actor, 1)),
            vv,
            vv,
        )


@pytest.mark.asyncio
async def test_store_merge_uses_crdt_and_vector_merge():
    actor0 = CausalActor("node-0", 1)
    actor1 = CausalActor("node-1", 1)
    left = StoredCrdtEntry(
        "views",
        CrdtType.GCOUNTER,
        GCounter().increment(actor0, 5),
        VersionVector({actor0: 1}),
        VersionVector({actor0: 1}),
    )
    right = StoredCrdtEntry(
        "views",
        CrdtType.GCOUNTER,
        GCounter().increment(actor1, 4),
        VersionVector({actor1: 1}),
        VersionVector({actor1: 1}),
    )
    store = CrdtStore()
    await store.put_if_absent(left)
    merged = await store.merge_entry(right)
    assert merged.state.value() == 9  # type: ignore[union-attr]
    assert merged.state_version == VersionVector({actor0: 1, actor1: 1})
    assert merged.causal_context == VersionVector({actor0: 1, actor1: 1})


@pytest.mark.asyncio
async def test_store_rejects_existing_key_type_change():
    actor = CausalActor("node-0", 1)
    store = CrdtStore()
    await store.put_if_absent(make_counter_entry("k", 1))
    bad = StoredCrdtEntry(
        "k",
        CrdtType.MVREGISTER,
        MVRegister().write("x", Dot(actor, 2)),
        VersionVector({actor: 2}),
        VersionVector({actor: 2}),
    )
    with pytest.raises(TypeError):
        await store.merge_entry(bad)


@pytest.mark.asyncio
async def test_same_key_lock_serializes_and_different_keys_can_progress():
    store = CrdtStore()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_same_entered = asyncio.Event()
    other_entered = asyncio.Event()

    async def first():
        async with store.key_lock("same"):
            first_entered.set()
            await release_first.wait()

    async def second_same():
        await first_entered.wait()
        async with store.key_lock("same"):
            second_same_entered.set()

    async def other():
        await first_entered.wait()
        async with store.key_lock("other"):
            other_entered.set()

    tasks = [
        asyncio.create_task(first()),
        asyncio.create_task(second_same()),
        asyncio.create_task(other()),
    ]
    await first_entered.wait()
    await asyncio.wait_for(other_entered.wait(), timeout=0.2)
    assert not second_same_entered.is_set()
    release_first.set()
    await asyncio.wait_for(second_same_entered.wait(), timeout=0.2)
    await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_snapshot_all_is_sorted_and_limited():
    store = CrdtStore()
    await store.put_if_absent(make_counter_entry("b", 1))
    await store.put_if_absent(make_counter_entry("a", 1))
    assert [e.key for e in await store.snapshot_all(limit=1)] == ["a"]
    assert await store.keys() == ("a", "b")
