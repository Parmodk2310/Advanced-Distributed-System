import pytest

from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.membership import MembershipTable


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def member(
    node_id: str,
    *,
    incarnation: int,
    status: MemberStatus = MemberStatus.ALIVE,
    port: int = 18000,
) -> ClusterMember:
    return ClusterMember(node_id, "127.0.0.1", port, status, incarnation)


def table(clock: FakeClock) -> MembershipTable:
    return MembershipTable(
        member("node-0", incarnation=100),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )


@pytest.mark.asyncio
async def test_higher_incarnation_replaces_complete_member_record():
    clock = FakeClock()
    membership = table(clock)
    await membership.merge([member("node-1", incarnation=10, port=18001)])

    changed = await membership.merge([member("node-1", incarnation=11, port=19001)])

    assert changed
    assert await membership.get("node-1") == member(
        "node-1",
        incarnation=11,
        port=19001,
    )


@pytest.mark.asyncio
async def test_stale_incarnation_is_ignored():
    clock = FakeClock()
    membership = table(clock)
    await membership.merge([member("node-1", incarnation=20, port=18001)])

    assert not await membership.merge(
        [
            member(
                "node-1",
                incarnation=19,
                status=MemberStatus.DEAD,
                port=19001,
            )
        ]
    )
    current = await membership.get("node-1")
    assert current is not None
    assert current.incarnation == 20


@pytest.mark.asyncio
async def test_equal_incarnation_more_severe_status_wins_without_address_change():
    clock = FakeClock()
    membership = table(clock)
    await membership.merge([member("node-1", incarnation=20, port=18001)])
    await membership.merge(
        [
            member(
                "node-1",
                incarnation=20,
                status=MemberStatus.SUSPECT,
                port=19001,
            )
        ]
    )

    assert await membership.get("node-1") == member(
        "node-1",
        incarnation=20,
        status=MemberStatus.SUSPECT,
        port=18001,
    )


@pytest.mark.asyncio
async def test_local_suspicion_self_refutes_with_newer_alive_incarnation():
    clock = FakeClock()
    membership = table(clock)

    await membership.merge([member("node-0", incarnation=100, status=MemberStatus.SUSPECT)])

    assert await membership.get("node-0") == member(
        "node-0",
        incarnation=101,
        status=MemberStatus.ALIVE,
    )


@pytest.mark.asyncio
async def test_suspect_becomes_dead_then_tombstone_blocks_stale_resurrection():
    clock = FakeClock()
    membership = table(clock)
    await membership.merge([member("node-1", incarnation=20, port=18001)])
    assert await membership.mark_suspect("node-1")

    clock.advance(3.1)
    assert await membership.advance_timeouts_and_purge()
    current = await membership.get("node-1")
    assert current is not None
    assert current.status is MemberStatus.DEAD

    assert not await membership.merge([member("node-1", incarnation=20, port=18001)])
    current = await membership.get("node-1")
    assert current is not None
    assert current.status is MemberStatus.DEAD


@pytest.mark.asyncio
async def test_dead_tombstone_is_purged_after_retention():
    clock = FakeClock()
    membership = table(clock)
    await membership.merge(
        [
            member(
                "node-1",
                incarnation=20,
                status=MemberStatus.DEAD,
                port=18001,
            )
        ]
    )

    clock.advance(30.1)
    assert await membership.advance_timeouts_and_purge()
    assert await membership.get("node-1") is None


@pytest.mark.asyncio
async def test_probe_candidates_include_suspect_but_not_dead():
    clock = FakeClock()
    membership = table(clock)
    await membership.merge(
        [
            member(
                "node-1",
                incarnation=20,
                status=MemberStatus.SUSPECT,
                port=18001,
            ),
            member(
                "node-2",
                incarnation=30,
                status=MemberStatus.DEAD,
                port=18002,
            ),
        ]
    )

    assert [item.node_id for item in await membership.probe_candidates()] == ["node-1"]
