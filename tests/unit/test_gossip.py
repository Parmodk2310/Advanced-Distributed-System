import pytest

from distsys.cluster.codec import AckData
from distsys.cluster.gossip import GossipLoop
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.membership import MembershipTable


def member(node_id: str, port: int, incarnation: int = 1) -> ClusterMember:
    return ClusterMember(
        node_id,
        "127.0.0.1",
        port,
        MemberStatus.ALIVE,
        incarnation,
    )


class FakePeerClient:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    async def gossip(self, peer, members, *, timeout_seconds):
        self.calls.append(peer.node_id)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


async def _noop() -> None:
    return None


def table_with_remote() -> MembershipTable:
    return MembershipTable(
        member("node-0", 18000),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
    )


@pytest.mark.asyncio
async def test_gossip_merges_returned_snapshot():
    table = table_with_remote()
    await table.merge([member("node-1", 18001)])
    peer = FakePeerClient(
        AckData(
            True,
            "node-1",
            (member("node-1", 18001), member("node-2", 18002)),
        )
    )
    changed = 0

    async def on_change() -> None:
        nonlocal changed
        changed += 1

    loop = GossipLoop(
        table=table,
        peer_client=peer,
        local_node_id="node-0",
        interval_seconds=1.0,
        timeout_seconds=0.25,
        on_membership_change=on_change,
        choose=lambda items: items[0],
    )

    await loop.run_once()

    assert await table.get("node-2") == member("node-2", 18002)
    assert changed == 1


@pytest.mark.asyncio
async def test_gossip_transport_failure_does_not_mark_peer_suspect():
    table = table_with_remote()
    await table.merge([member("node-1", 18001)])
    peer = FakePeerClient(ConnectionRefusedError())
    loop = GossipLoop(
        table=table,
        peer_client=peer,
        local_node_id="node-0",
        interval_seconds=1.0,
        timeout_seconds=0.25,
        on_membership_change=_noop,
        choose=lambda items: items[0],
    )

    await loop.run_once()

    current = await table.get("node-1")
    assert current is not None
    assert current.status is MemberStatus.ALIVE
