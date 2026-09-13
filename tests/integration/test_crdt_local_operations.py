import pytest

from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.crdt import CrdtType
from distsys.crdt_service import CrdtService
from distsys.replication.codec import CrdtMutationData, CrdtReadData
from distsys.resilience.deadline import Deadline
from distsys.utils.config import Settings


class Membership:
    def __init__(self, members):
        self.members = tuple(members)

    async def alive_members(self, *, include_self=True):
        if include_self:
            return self.members
        return tuple(m for m in self.members if m.node_id != "node-0")


class ClusterStub:
    def __init__(self):
        self.local_member = ClusterMember("node-0", "127.0.0.1", 18000, MemberStatus.ALIVE, 123)
        self.ring = ConsistentHashRing(virtual_nodes=16)
        self.ring.rebuild((self.local_member,))
        self.membership = Membership((self.local_member,))


class UnusedPeer:
    pass


def service() -> CrdtService:
    return CrdtService(
        settings=Settings(
            node_id="node-0",
            host="127.0.0.1",
            port=18000,
            cluster_enabled=True,
            crdt_enabled=True,
        ),
        cluster_service=ClusterStub(),  # type: ignore[arg-type]
        peer_client=UnusedPeer(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_gcounter_and_pncounter_local_operations():
    svc = service()
    first = await svc.mutate(
        CrdtMutationData("views", CrdtType.GCOUNTER, "increment", amount=3),
        Deadline.after(1),
    )
    assert first.success and first.value == 3
    second = await svc.mutate(
        CrdtMutationData("balance", CrdtType.PNCOUNTER, "increment", amount=10),
        Deadline.after(1),
    )
    assert second.success and second.value == 10
    third = await svc.mutate(
        CrdtMutationData(
            "balance",
            CrdtType.PNCOUNTER,
            "decrement",
            amount=4,
            causal_token=second.causal_token,
        ),
        Deadline.after(1),
    )
    assert third.success and third.value == 6


@pytest.mark.asyncio
async def test_orset_and_mvregister_local_operations():
    svc = service()
    added = await svc.mutate(
        CrdtMutationData("tags", CrdtType.ORSET, "add", value="python"),
        Deadline.after(1),
    )
    assert added.value == ["python"]
    removed = await svc.mutate(
        CrdtMutationData(
            "tags",
            CrdtType.ORSET,
            "remove",
            value="python",
            causal_token=added.causal_token,
        ),
        Deadline.after(1),
    )
    assert removed.value == []
    reg = await svc.mutate(
        CrdtMutationData("status", CrdtType.MVREGISTER, "write", value={"risk": "medium"}),
        Deadline.after(1),
    )
    assert reg.value == [{"risk": "medium"}]


@pytest.mark.asyncio
async def test_read_returns_key_not_found():
    svc = service()
    result = await svc.read(CrdtReadData("missing"), Deadline.after(1))
    assert not result.success
    assert result.error_code != 0


@pytest.mark.asyncio
async def test_successful_write_returns_incarnation_scoped_token():
    svc = service()
    result = await svc.mutate(
        CrdtMutationData("views", CrdtType.GCOUNTER, "increment", amount=1),
        Deadline.after(1),
    )
    actors = [actor for actor, _ in result.causal_token.version.items()]
    assert actors[0].node_id == "node-0"
    assert actors[0].incarnation == 123
