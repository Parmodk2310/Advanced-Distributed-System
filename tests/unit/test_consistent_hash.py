import pytest

from distsys.cluster.consistent_hash import ConsistentHashRing, NoRouteError
from distsys.cluster.member import ClusterMember, MemberStatus


def member(
    node_id: str,
    port: int,
    status: MemberStatus = MemberStatus.ALIVE,
) -> ClusterMember:
    return ClusterMember(node_id, "127.0.0.1", port, status, 1)


def test_identical_membership_builds_identical_ownership():
    members = [
        member("node-0", 18000),
        member("node-1", 18001),
        member("node-2", 18002),
    ]
    left = ConsistentHashRing(virtual_nodes=64)
    right = ConsistentHashRing(virtual_nodes=64)
    left.rebuild(members)
    right.rebuild(reversed(members))

    assert [left.owner(f"key-{index}").node_id for index in range(100)] == [
        right.owner(f"key-{index}").node_id for index in range(100)
    ]


def test_only_alive_members_participate():
    ring = ConsistentHashRing(virtual_nodes=64)
    ring.rebuild(
        [
            member("node-0", 18000),
            member("node-1", 18001, MemberStatus.SUSPECT),
            member("node-2", 18002, MemberStatus.DEAD),
        ]
    )

    assert {ring.owner(f"key-{index}").node_id for index in range(20)} == {"node-0"}


def test_candidates_are_unique_physical_members():
    ring = ConsistentHashRing(virtual_nodes=64)
    ring.rebuild(
        [
            member("node-0", 18000),
            member("node-1", 18001),
            member("node-2", 18002),
        ]
    )

    candidates = ring.candidates("customer-123")
    assert len(candidates) == 3
    assert len({candidate.node_id for candidate in candidates}) == 3
    assert candidates[0] == ring.owner("customer-123")


def test_removing_member_only_moves_keys_owned_by_that_member():
    members = [
        member("node-0", 18000),
        member("node-1", 18001),
        member("node-2", 18002),
    ]
    before = ConsistentHashRing(virtual_nodes=64)
    before.rebuild(members)
    previous = {f"key-{index}": before.owner(f"key-{index}").node_id for index in range(500)}

    after = ConsistentHashRing(virtual_nodes=64)
    after.rebuild(members[:2])

    for key, old_owner in previous.items():
        if old_owner != "node-2":
            assert after.owner(key).node_id == old_owner


def test_empty_ring_raises_no_route():
    ring = ConsistentHashRing()
    with pytest.raises(NoRouteError):
        ring.owner("customer-123")
    with pytest.raises(NoRouteError):
        ring.candidates("customer-123")
