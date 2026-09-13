import pytest

from distsys.cluster.codec import (
    AckData,
    decode_ack,
    decode_join_response,
    encode_join_request,
    encode_ping,
    encode_ping_request,
)
from distsys.cluster.member import ClusterMember, MemberStatus, SeedAddress
from distsys.cluster.service import ClusterBootstrapError, ClusterService
from distsys.protocol.message import Message, MessageType
from distsys.resilience.deadline import Deadline
from distsys.utils.config import Settings


def member(node_id: str, port: int, incarnation: int = 10) -> ClusterMember:
    return ClusterMember(
        node_id,
        "127.0.0.1",
        port,
        MemberStatus.ALIVE,
        incarnation,
    )


class FakePeerClient:
    def __init__(self) -> None:
        self.join_outcomes: dict[tuple[str, int], object] = {}
        self.ping_outcomes: dict[str, object] = {}

    async def join(self, seed, local_member, *, timeout_seconds):
        outcome = self.join_outcomes[(seed.host, seed.port)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def ping(self, peer, gossip, *, timeout_seconds):
        outcome = self.ping_outcomes[peer.node_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def ping_request(self, helper, target, gossip, *, timeout_seconds):
        raise AssertionError("not used")

    async def gossip(self, peer, members, *, timeout_seconds):
        return AckData(True, peer.node_id, members)

    async def forward_task(self, peer, **kwargs):
        raise AssertionError("not used")


async def local_execute(task_name, payload, deadline: Deadline):
    return {"task": task_name}


def settings_for(
    node_id: str,
    port: int,
    *,
    seeds: tuple[SeedAddress, ...] = (),
) -> Settings:
    return Settings(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        cluster_enabled=True,
        cluster_seeds=seeds,
    )


@pytest.mark.asyncio
async def test_seed_bootstrap_merges_snapshot_and_rebuilds_ring():
    settings = settings_for(
        "node-1",
        18001,
        seeds=(SeedAddress("127.0.0.1", 18000),),
    )
    peer = FakePeerClient()
    peer.join_outcomes[("127.0.0.1", 18000)] = (
        member("node-0", 18000),
        member("node-1", 18001, 20),
    )
    service = ClusterService(
        settings=settings,
        bound_port=18001,
        execute_local=local_execute,
        peer_client=peer,
        incarnation=20,
    )

    await service.bootstrap()

    assert {item.node_id for item in await service.membership.snapshot()} == {
        "node-0",
        "node-1",
    }
    assert {item.node_id for item in service.ring.candidates("key")} == {
        "node-0",
        "node-1",
    }


@pytest.mark.asyncio
async def test_configured_seed_failure_fails_bootstrap():
    settings = settings_for(
        "node-1",
        18001,
        seeds=(SeedAddress("127.0.0.1", 18000),),
    )
    peer = FakePeerClient()
    peer.join_outcomes[("127.0.0.1", 18000)] = ConnectionRefusedError()
    service = ClusterService(
        settings=settings,
        bound_port=18001,
        execute_local=local_execute,
        peer_client=peer,
        incarnation=20,
    )

    with pytest.raises(ClusterBootstrapError):
        await service.bootstrap()


@pytest.mark.asyncio
async def test_join_request_merges_member_and_returns_snapshot():
    settings = settings_for("node-0", 18000)
    service = ClusterService(
        settings=settings,
        bound_port=18000,
        execute_local=local_execute,
        peer_client=FakePeerClient(),
        incarnation=10,
    )
    joining = member("node-1", 18001, 20)
    request = Message.new_request(
        sender_id="node-1",
        msg_type=MessageType.JOIN_REQUEST,
        payload=encode_join_request(joining),
    )

    response = await service.handle_control(request)

    assert response.msg_type is MessageType.JOIN_RESPONSE
    assert {item.node_id for item in decode_join_response(response.payload)} == {
        "node-0",
        "node-1",
    }


@pytest.mark.asyncio
async def test_ping_merges_gossip_and_returns_ack_snapshot():
    settings = settings_for("node-0", 18000)
    service = ClusterService(
        settings=settings,
        bound_port=18000,
        execute_local=local_execute,
        peer_client=FakePeerClient(),
        incarnation=10,
    )
    remote = member("node-1", 18001, 20)
    request = Message.new_request(
        sender_id="node-1",
        msg_type=MessageType.PING,
        payload=encode_ping((remote,)),
    )

    response = await service.handle_control(request)
    ack = decode_ack(response.payload)

    assert response.msg_type is MessageType.ACK
    assert ack.success is True
    assert ack.target_node_id == "node-0"
    assert {item.node_id for item in ack.gossip} == {"node-0", "node-1"}


@pytest.mark.asyncio
async def test_ping_request_reports_target_success():
    settings = settings_for("node-2", 18002)
    peer = FakePeerClient()
    target = member("node-1", 18001, 20)
    peer.ping_outcomes["node-1"] = AckData(True, "node-1", (target,))
    service = ClusterService(
        settings=settings,
        bound_port=18002,
        execute_local=local_execute,
        peer_client=peer,
        incarnation=30,
    )
    request = Message.new_request(
        sender_id="node-0",
        msg_type=MessageType.PING_REQ,
        payload=encode_ping_request(target=target, gossip=()),
    )

    ack = decode_ack((await service.handle_control(request)).payload)

    assert ack.success is True
    assert ack.target_node_id == "node-1"
