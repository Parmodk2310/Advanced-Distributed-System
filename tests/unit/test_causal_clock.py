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
