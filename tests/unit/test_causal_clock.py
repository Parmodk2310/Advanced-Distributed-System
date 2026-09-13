import pytest

from distsys.causal import CausalActor, VersionVector
from distsys.causal.clock import CausalClock


@pytest.mark.asyncio
async def test_counter_increases_and_frontier_tracks_local_actor():
    actor = CausalActor("node-0", 100)
    clock = CausalClock(actor)
    d1, _ = await clock.allocate()
    d2, frontier = await clock.allocate()
    assert (d1.counter, d2.counter) == (1, 2)
    assert frontier.get(actor) == 2


@pytest.mark.asyncio
async def test_allocate_merges_observed_frontier_first():
    local = CausalActor("node-0", 100)
    remote = CausalActor("node-1", 200)
    clock = CausalClock(local)
    dot, frontier = await clock.allocate(VersionVector({remote: 7}))
    assert dot.actor == local
    assert frontier.get(remote) == 7
    assert frontier.get(local) == 1


@pytest.mark.asyncio
async def test_new_incarnation_can_restart_counter_without_dot_collision():
    old = CausalClock(CausalActor("node-0", 100))
    new = CausalClock(CausalActor("node-0", 101))
    old_dot, _ = await old.allocate()
    new_dot, _ = await new.allocate()
    assert old_dot != new_dot
    assert old_dot.counter == new_dot.counter == 1


@pytest.mark.asyncio
async def test_observe_updates_frontier_without_allocating_local_event():
    local = CausalActor("node-0", 100)
    remote = CausalActor("node-1", 200)
    clock = CausalClock(local)
    observed = await clock.observe(VersionVector({remote: 9}))
    assert observed.get(remote) == 9
    assert observed.get(local) == 0


@pytest.mark.asyncio
async def test_staged_allocation_without_commit_does_not_advance_clock():
    actor = CausalActor("node-0", 500)
    clock = CausalClock(actor)
    before = await clock.frontier()
    async with clock.staged_allocation() as allocation:
        assert allocation.dot.counter == 1
    assert await clock.frontier() == before


@pytest.mark.asyncio
async def test_staged_allocation_commit_advances_clock():
    actor = CausalActor("node-0", 500)
    clock = CausalClock(actor)
    async with clock.staged_allocation() as allocation:
        allocation.commit()
        expected = allocation.frontier
    assert await clock.frontier() == expected


@pytest.mark.asyncio
async def test_staged_allocation_exception_rolls_back_clock():
    actor = CausalActor("node-0", 500)
    clock = CausalClock(actor)
    with pytest.raises(RuntimeError):
        async with clock.staged_allocation() as allocation:
            allocation.commit()
            raise RuntimeError("disk failed")
    assert await clock.frontier() == VersionVector()


@pytest.mark.asyncio
async def test_restore_replaces_clock_frontier_for_same_actor():
    actor = CausalActor("node-0", 500)
    clock = CausalClock(actor)
    restored = VersionVector({actor: 11, CausalActor("peer", 9): 4})
    await clock.restore(restored)
    assert await clock.frontier() == restored


@pytest.mark.asyncio
async def test_staged_observe_rolls_back_without_commit():
    actor = CausalActor("node-0", 500)
    remote = CausalActor("node-1", 700)
    clock = CausalClock(actor)
    async with clock.staged_observe(VersionVector({remote: 4})) as observation:
        assert observation.frontier.get(remote) == 4
    assert await clock.frontier() == VersionVector()


@pytest.mark.asyncio
async def test_staged_observe_commits_frontier():
    actor = CausalActor("node-0", 500)
    remote = CausalActor("node-1", 700)
    clock = CausalClock(actor)
    async with clock.staged_observe(VersionVector({remote: 4})) as observation:
        observation.commit()
    assert (await clock.frontier()).get(remote) == 4
