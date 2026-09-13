import pytest

from distsys.cluster.codec import AckData
from distsys.cluster.failure_detector import FailureDetector
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
    port: int,
    status: MemberStatus = MemberStatus.ALIVE,
) -> ClusterMember:
    return ClusterMember(node_id, "127.0.0.1", port, status, 10)


class FakePeerClient:
    def __init__(self) -> None:
        self.direct: dict[str, object] = {}
        self.indirect: dict[tuple[str, str], object] = {}
        self.ping_calls: list[str] = []
        self.ping_req_calls: list[tuple[str, str]] = []

    async def ping(self, peer, gossip, *, timeout_seconds):
        self.ping_calls.append(peer.node_id)
        outcome = self.direct[peer.node_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def ping_request(self, helper, target, gossip, *, timeout_seconds):
        self.ping_req_calls.append((helper.node_id, target.node_id))
        outcome = self.indirect[(helper.node_id, target.node_id)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


async def _noop() -> None:
    return None


def detector(
    *,
    table: MembershipTable,
    peer: FakePeerClient,
    choose,
    indirect_probe_count: int = 2,
    on_change=_noop,
) -> FailureDetector:
    return FailureDetector(
        table=table,
        peer_client=peer,
        local_node_id="node-0",
        probe_interval_seconds=1.0,
        ping_timeout_seconds=0.25,
        indirect_timeout_seconds=0.5,
        indirect_probe_count=indirect_probe_count,
        on_membership_change=on_change,
        choose=choose,
    )


@pytest.mark.asyncio
async def test_direct_probe_success_keeps_target_alive():
    clock = FakeClock()
    local = member("node-0", 18000)
    target = member("node-1", 18001)
    table = MembershipTable(
        local,
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([target])
    peer = FakePeerClient()
    peer.direct["node-1"] = AckData(True, "node-1", (target,))

    await detector(table=table, peer=peer, choose=lambda items: items[0]).run_once()

    current = await table.get("node-1")
    assert current is not None
    assert current.status is MemberStatus.ALIVE


@pytest.mark.asyncio
async def test_indirect_probe_success_avoids_suspicion():
    clock = FakeClock()
    local = member("node-0", 18000)
    target = member("node-1", 18001)
    helper = member("node-2", 18002)
    table = MembershipTable(
        local,
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([target, helper])
    peer = FakePeerClient()
    peer.direct["node-1"] = ConnectionRefusedError()
    peer.indirect[("node-2", "node-1")] = AckData(
        True,
        "node-1",
        (target, helper),
    )

    await detector(
        table=table,
        peer=peer,
        choose=lambda items: next(item for item in items if item.node_id == "node-1"),
    ).run_once()

    current = await table.get("node-1")
    assert current is not None
    assert current.status is MemberStatus.ALIVE
    assert peer.ping_req_calls == [("node-2", "node-1")]


@pytest.mark.asyncio
async def test_failed_direct_and_indirect_marks_suspect():
    clock = FakeClock()
    local = member("node-0", 18000)
    target = member("node-1", 18001)
    helper = member("node-2", 18002)
    table = MembershipTable(
        local,
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([target, helper])
    peer = FakePeerClient()
    peer.direct["node-1"] = TimeoutError()
    peer.indirect[("node-2", "node-1")] = TimeoutError()
    changes = 0

    async def changed() -> None:
        nonlocal changes
        changes += 1

    await detector(
        table=table,
        peer=peer,
        on_change=changed,
        choose=lambda items: next(item for item in items if item.node_id == "node-1"),
    ).run_once()

    current = await table.get("node-1")
    assert current is not None
    assert current.status is MemberStatus.SUSPECT
    assert changes >= 1


@pytest.mark.asyncio
async def test_expired_suspicion_becomes_dead_before_next_probe():
    clock = FakeClock()
    local = member("node-0", 18000)
    target = member("node-1", 18001)
    table = MembershipTable(
        local,
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([target])
    await table.mark_suspect("node-1")
    clock.advance(3.1)
    peer = FakePeerClient()
    peer.direct["node-1"] = TimeoutError()

    await detector(
        table=table,
        peer=peer,
        choose=lambda items: items[0],
        indirect_probe_count=0,
    ).run_once()

    current = await table.get("node-1")
    assert current is not None
    assert current.status is MemberStatus.DEAD
