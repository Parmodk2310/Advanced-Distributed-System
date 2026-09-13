import pytest

from distsys.causal import CausalActor, Dot, VersionVector
from distsys.crdt import CrdtType, GCounter
from distsys.replication.outbox import ReplicationBackpressureError, ReplicationOutbox
from distsys.storage import StoredCrdtEntry


def entry(key: str, n: int) -> StoredCrdtEntry:
    actor = CausalActor("node-0", 1)
    state = GCounter().increment(actor, n)
    vv = VersionVector().with_dot(Dot(actor, n))
    return StoredCrdtEntry(key, CrdtType.GCOUNTER, state, vv, vv)


@pytest.mark.asyncio
async def test_new_pair_consumes_capacity_and_second_new_pair_is_rejected():
    outbox = ReplicationOutbox(capacity=1)
    reservation = await outbox.reserve((("node-1", "k1"),))
    await outbox.publish(reservation, {"k1": entry("k1", 1)})
    assert await outbox.pending_count() == 1
    with pytest.raises(ReplicationBackpressureError):
        await outbox.reserve((("node-2", "k2"),))


@pytest.mark.asyncio
async def test_existing_pair_coalesces_without_extra_capacity():
    outbox = ReplicationOutbox(capacity=1)
    first = await outbox.reserve((("node-1", "k"),))
    await outbox.publish(first, {"k": entry("k", 1)})
    second = await outbox.reserve((("node-1", "k"),))
    await outbox.publish(second, {"k": entry("k", 2)})
    assert await outbox.pending_count() == 1


@pytest.mark.asyncio
async def test_multi_peer_reservation_is_all_or_nothing():
    outbox = ReplicationOutbox(capacity=1)
    with pytest.raises(ReplicationBackpressureError):
        await outbox.reserve((("node-1", "k"), ("node-2", "k")))
    assert await outbox.pending_count() == 0


@pytest.mark.asyncio
async def test_old_generation_completion_does_not_drop_newer_state():
    outbox = ReplicationOutbox(capacity=1)
    r1 = await outbox.reserve((("node-1", "k"),))
    await outbox.publish(r1, {"k": entry("k", 1)})
    first = await outbox.next_ready()
    assert first.generation == 1

    r2 = await outbox.reserve((("node-1", "k"),))
    await outbox.publish(r2, {"k": entry("k", 2)})
    await outbox.complete("node-1", "k", first.generation)

    second = await outbox.next_ready()
    assert second.generation == 2
    assert second.state.state.value() == 2  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_reserved_follow_up_survives_completion_of_in_flight_generation():
    outbox = ReplicationOutbox(capacity=1)
    first_reservation = await outbox.reserve((("node-1", "k"),))
    await outbox.publish(first_reservation, {"k": entry("k", 1)})
    first = await outbox.next_ready()

    follow_up = await outbox.reserve((("node-1", "k"),))
    await outbox.complete("node-1", "k", first.generation)

    await outbox.publish(follow_up, {"k": entry("k", 2)})
    second = await outbox.next_ready()
    assert second.generation == 2
    assert second.state.state.value() == 2  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_cancelled_follow_up_releases_completed_placeholder():
    outbox = ReplicationOutbox(capacity=1)
    first_reservation = await outbox.reserve((("node-1", "k"),))
    await outbox.publish(first_reservation, {"k": entry("k", 1)})
    first = await outbox.next_ready()

    follow_up = await outbox.reserve((("node-1", "k"),))
    await outbox.complete("node-1", "k", first.generation)
    assert await outbox.pending_count() == 1

    await outbox.cancel(follow_up)
    assert await outbox.pending_count() == 0
