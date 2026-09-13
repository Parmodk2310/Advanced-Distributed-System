import pytest

from distsys.coordination.models import (
    CoordinationMember,
    member_key,
    node_metadata_key,
)


def test_coordination_member_round_trip_is_canonical():
    member = CoordinationMember(
        node_id="node-1",
        node_uuid="uuid-1",
        host="127.0.0.1",
        port=18001,
        membership_incarnation=55,
        protocol_version=5,
        release="0.5.0",
        tls_required=True,
    )
    assert CoordinationMember.from_json(member.to_json()) == member


def test_namespace_keys_are_versioned():
    assert member_key("/distsys/v1", "node-1") == "/distsys/v1/members/node-1"
    assert node_metadata_key("/distsys/v1", "node-1") == "/distsys/v1/nodes/node-1/metadata"


def test_member_rejects_invalid_port():
    with pytest.raises(ValueError):
        CoordinationMember("n", "u", "h", 0, 1, 5, "0.5.0", False)
