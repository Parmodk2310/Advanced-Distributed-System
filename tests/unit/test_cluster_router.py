from typing import Any

import pytest

from distsys.cluster.cluster_router import (
    ClusterRouter,
    LocalOverloadedError,
    PeerUnavailableError,
)
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.peer_client import PeerApplicationError, PeerTransportError
from distsys.proto import messages_pb2
from distsys.resilience.deadline import Deadline


def member(node_id: str, port: int) -> ClusterMember:
    return ClusterMember(node_id, "127.0.0.1", port, MemberStatus.ALIVE, 1)


class FakePeerClient:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    async def forward_task(self, peer, **kwargs):
        self.calls.append(peer.node_id)
        outcome = self.outcomes[peer.node_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_local_owner_executes_locally():
    local = member("node-0", 18000)
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild([local])
    calls: list[str] = []

    async def execute_local(task_name: str, payload: Any, deadline: Deadline):
        calls.append(task_name)
        return {"node_id": "node-0"}

    router = ClusterRouter(
        local_node_id="node-0",
        ring=ring,
        peer_client=FakePeerClient({}),
        execute_local=execute_local,
    )

    assert await router.execute(
        "cluster.whoami",
        {},
        routing_key="key",
        deadline=Deadline.after(1.0),
    ) == {"node_id": "node-0"}
    assert calls == ["cluster.whoami"]


@pytest.mark.asyncio
async def test_transport_failure_fails_over_to_next_candidate():
    nodes = [
        member("node-0", 18000),
        member("node-1", 18001),
        member("node-2", 18002),
    ]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(nodes)
    key = next(
        f"key-{index}" for index in range(1000) if ring.owner(f"key-{index}").node_id == "node-1"
    )
    peer = FakePeerClient(
        {
            "node-1": PeerTransportError("down"),
            "node-2": {"node_id": "node-2"},
            "node-0": {"node_id": "node-0"},
        }
    )

    async def execute_local(task_name, payload, deadline):
        return {"node_id": "node-0"}

    router = ClusterRouter(
        local_node_id="node-0",
        ring=ring,
        peer_client=peer,
        execute_local=execute_local,
    )
    result = await router.execute(
        "cluster.whoami",
        {},
        routing_key=key,
        deadline=Deadline.after(1.0),
    )

    assert result["node_id"] != "node-1"
    assert peer.calls[0] == "node-1"


@pytest.mark.asyncio
async def test_invalid_request_is_returned_without_failover():
    nodes = [member("node-0", 18000), member("node-1", 18001)]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(nodes)
    key = next(
        f"key-{index}" for index in range(1000) if ring.owner(f"key-{index}").node_id == "node-1"
    )
    peer = FakePeerClient(
        {"node-1": PeerApplicationError(messages_pb2.INVALID_REQUEST, "bad payload")}
    )

    async def execute_local(task_name, payload, deadline):
        return {"node_id": "node-0"}

    router = ClusterRouter(
        local_node_id="node-0",
        ring=ring,
        peer_client=peer,
        execute_local=execute_local,
    )

    with pytest.raises(PeerApplicationError) as exc:
        await router.execute(
            "echo",
            {},
            routing_key=key,
            deadline=Deadline.after(1.0),
        )

    assert exc.value.code == messages_pb2.INVALID_REQUEST
    assert peer.calls == ["node-1"]


@pytest.mark.asyncio
async def test_local_overload_fails_over():
    nodes = [member("node-0", 18000), member("node-1", 18001)]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(nodes)
    key = next(
        f"key-{index}" for index in range(1000) if ring.owner(f"key-{index}").node_id == "node-0"
    )
    peer = FakePeerClient({"node-1": {"node_id": "node-1"}})

    async def execute_local(task_name, payload, deadline):
        raise LocalOverloadedError("busy")

    router = ClusterRouter(
        local_node_id="node-0",
        ring=ring,
        peer_client=peer,
        execute_local=execute_local,
    )

    assert await router.execute(
        "echo",
        {},
        routing_key=key,
        deadline=Deadline.after(1.0),
    ) == {"node_id": "node-1"}


@pytest.mark.asyncio
async def test_all_failover_candidates_exhausted_raises_peer_unavailable():
    nodes = [member("node-1", 18001), member("node-2", 18002)]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(nodes)
    peer = FakePeerClient(
        {
            "node-1": PeerTransportError("down"),
            "node-2": PeerApplicationError(messages_pb2.OVERLOADED, "busy"),
        }
    )

    async def execute_local(task_name, payload, deadline):
        raise AssertionError("local execution is not expected")

    router = ClusterRouter(
        local_node_id="node-0",
        ring=ring,
        peer_client=peer,
        execute_local=execute_local,
    )

    with pytest.raises(PeerUnavailableError):
        await router.execute(
            "echo",
            {},
            routing_key="key",
            deadline=Deadline.after(1.0),
        )
