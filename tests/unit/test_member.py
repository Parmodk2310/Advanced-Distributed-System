import pytest

from distsys.cluster.member import (
    ClusterMember,
    MemberStatus,
    SeedAddress,
    fresh_incarnation,
)


def test_member_status_severity_order_is_stable():
    assert MemberStatus.ALIVE < MemberStatus.SUSPECT < MemberStatus.DEAD


def test_cluster_member_is_immutable():
    member = ClusterMember(
        "node-1",
        "127.0.0.1",
        18001,
        MemberStatus.ALIVE,
        10,
    )
    with pytest.raises(AttributeError):
        member.status = MemberStatus.DEAD  # type: ignore[misc]


def test_seed_address_parses_host_and_port():
    assert SeedAddress.parse("127.0.0.1:18000") == SeedAddress(
        "127.0.0.1",
        18000,
    )


@pytest.mark.parametrize(
    "raw",
    ["", "127.0.0.1", ":18000", "host:0", "host:65536", "host:not-a-port"],
)
def test_seed_address_rejects_invalid_values(raw: str):
    with pytest.raises(ValueError):
        SeedAddress.parse(raw)


def test_fresh_incarnation_is_positive_and_non_decreasing():
    first = fresh_incarnation()
    second = fresh_incarnation()
    assert first > 0
    assert second >= first
