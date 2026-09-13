import logging
from typing import Any

import pytest

from distsys.cluster.cluster_router import ClusterRouter
from distsys.cluster.codec import AckData
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.gossip import GossipLoop
from distsys.cluster.member import ClusterMember, MemberStatus, SeedAddress
from distsys.cluster.membership import MembershipTable
from distsys.cluster.peer_client import PeerTransportError
from distsys.cluster.service import ClusterService
from distsys.resilience.deadline import Deadline
from distsys.utils.config import Settings


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def member(
    node_id: str,
    status: MemberStatus = MemberStatus.ALIVE,
    incarnation: int = 10,
) -> ClusterMember:
    return ClusterMember(
        node_id=node_id,
        host="127.0.0.1",
        port=18000 if node_id == "node-0" else 18001,
        status=status,
        incarnation=incarnation,
    )


def events(caplog: pytest.LogCaptureFixture) -> list[str]:
    recorded: list[str] = []
    for record in caplog.records:
        event = record.__dict__.get("event")
        if isinstance(event, str):
            recorded.append(event)
    return recorded


@pytest.mark.asyncio
async def test_membership_logs_suspect_dead_and_self_refutation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="distsys.cluster.membership")
    clock = FakeClock()
    table = MembershipTable(
        member("node-0"),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([member("node-1")])
    await table.mark_suspect("node-1")
    clock.advance(3.1)
    await table.advance_timeouts_and_purge()
    await table.merge([member("node-0", MemberStatus.SUSPECT, incarnation=10)])

    recorded = events(caplog)
    assert "member_suspect" in recorded
    assert "member_dead" in recorded
    assert "member_refuted" in recorded


class RouterPeer:
    async def forward_task(
        self,
        peer: ClusterMember,
        *,
        task_name: str,
        payload: Any,
        routing_key: str,
        origin_node_id: str,
        deadline: Deadline,
    ) -> Any:
        del task_name, payload, routing_key, origin_node_id, deadline
        raise PeerTransportError(f"{peer.node_id} is down")


@pytest.mark.asyncio
async def test_router_logs_route_failover(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="distsys.cluster.cluster_router")
    remote = ClusterMember(
        "node-1",
        "127.0.0.1",
        18001,
        MemberStatus.ALIVE,
        1,
    )
    local = ClusterMember(
        "node-0",
        "127.0.0.1",
        18000,
        MemberStatus.ALIVE,
        1,
    )
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild((local, remote))
    key = next(
        f"route-{index}"
        for index in range(1_000)
        if ring.owner(f"route-{index}").node_id == "node-1"
    )

    async def execute_local(
        task_name: str,
        payload: Any,
        deadline: Deadline,
    ) -> Any:
        del task_name, payload, deadline
        return {"node_id": "node-0"}

    router = ClusterRouter(
        local_node_id="node-0",
        ring=ring,
        peer_client=RouterPeer(),
        execute_local=execute_local,
    )

    assert await router.execute(
        "cluster.whoami",
        {},
        routing_key=key,
        deadline=Deadline.after(1.0),
    ) == {"node_id": "node-0"}
    assert "route_failover" in events(caplog)


class GossipPeer:
    def __init__(self, outcome: AckData | BaseException) -> None:
        self.outcome = outcome

    async def gossip(
        self,
        peer: ClusterMember,
        members: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData:
        del peer, members, timeout_seconds
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


async def _noop_change() -> None:
    return None


@pytest.mark.asyncio
async def test_gossip_logs_success_and_failure(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="distsys.cluster.gossip")
    table = MembershipTable(
        member("node-0"),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
    )
    remote = member("node-1")
    await table.merge((remote,))

    success = GossipLoop(
        table=table,
        peer_client=GossipPeer(AckData(True, "node-1", (remote,))),
        local_node_id="node-0",
        interval_seconds=1.0,
        timeout_seconds=0.25,
        on_membership_change=_noop_change,
        choose=lambda items: items[0],
    )
    await success.run_once()

    failure = GossipLoop(
        table=table,
        peer_client=GossipPeer(ConnectionRefusedError()),
        local_node_id="node-0",
        interval_seconds=1.0,
        timeout_seconds=0.25,
        on_membership_change=_noop_change,
        choose=lambda items: items[0],
    )
    await failure.run_once()

    recorded = events(caplog)
    assert "cluster_gossip_sent" in recorded
    assert "cluster_gossip_failed" in recorded


class BootstrapPeer:
    async def join(
        self,
        seed: SeedAddress,
        local_member: ClusterMember,
        *,
        timeout_seconds: float,
    ) -> tuple[ClusterMember, ...]:
        del timeout_seconds
        return (
            ClusterMember(
                "node-0",
                "127.0.0.1",
                seed.port,
                MemberStatus.ALIVE,
                10,
            ),
            local_member,
        )

    async def ping(
        self,
        peer: ClusterMember,
        gossip: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData:
        del timeout_seconds
        return AckData(True, peer.node_id, gossip)

    async def ping_request(
        self,
        helper: ClusterMember,
        target: ClusterMember,
        gossip: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData:
        del helper, timeout_seconds
        return AckData(True, target.node_id, gossip)

    async def gossip(
        self,
        peer: ClusterMember,
        members: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData:
        del timeout_seconds
        return AckData(True, peer.node_id, members)

    async def forward_task(
        self,
        peer: ClusterMember,
        *,
        task_name: str,
        payload: Any,
        routing_key: str,
        origin_node_id: str,
        deadline: Deadline,
    ) -> Any:
        del peer, task_name, payload, routing_key, origin_node_id, deadline
        raise AssertionError("not used")


@pytest.mark.asyncio
async def test_service_logs_membership_change_and_join(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="distsys.cluster.service")

    async def execute_local(
        task_name: str,
        payload: Any,
        deadline: Deadline,
    ) -> Any:
        del task_name, deadline
        return payload

    settings = Settings(
        node_id="node-1",
        host="127.0.0.1",
        port=18001,
        cluster_enabled=True,
        cluster_seeds=(SeedAddress("127.0.0.1", 18000),),
    )
    service = ClusterService(
        settings=settings,
        bound_port=18001,
        execute_local=execute_local,
        peer_client=BootstrapPeer(),
        incarnation=20,
    )

    await service.bootstrap()

    recorded = events(caplog)
    assert "membership_changed" in recorded
    assert "cluster_joined" in recorded
