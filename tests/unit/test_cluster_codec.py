from distsys.cluster.codec import (
    decode_ack,
    decode_forwarded_request,
    decode_gossip,
    decode_join_request,
    decode_join_response,
    decode_ping,
    decode_ping_request,
    encode_ack,
    encode_forwarded_request,
    encode_gossip,
    encode_join_request,
    encode_join_response,
    encode_ping,
    encode_ping_request,
)
from distsys.cluster.member import ClusterMember, MemberStatus


def member(node_id: str, port: int, incarnation: int = 10) -> ClusterMember:
    return ClusterMember(node_id, "127.0.0.1", port, MemberStatus.ALIVE, incarnation)


def test_join_round_trip():
    local = member("node-1", 18001)
    assert decode_join_request(encode_join_request(local)) == local
    snapshot = (member("node-0", 18000), local)
    assert decode_join_response(encode_join_response(snapshot)) == snapshot


def test_ping_ack_and_ping_request_round_trip():
    snapshot = (member("node-0", 18000), member("node-1", 18001))
    assert decode_ping(encode_ping(snapshot)) == snapshot
    ack = decode_ack(encode_ack(success=True, target_node_id="node-1", gossip=snapshot))
    assert ack.success is True
    assert ack.target_node_id == "node-1"
    assert ack.gossip == snapshot
    target, gossip = decode_ping_request(
        encode_ping_request(target=member("node-1", 18001), gossip=snapshot)
    )
    assert target == member("node-1", 18001)
    assert gossip == snapshot


def test_gossip_round_trip():
    snapshot = (member("node-0", 18000), member("node-1", 18001))
    assert decode_gossip(encode_gossip(snapshot)) == snapshot


def test_forwarded_task_round_trip():
    encoded = encode_forwarded_request(
        task_name="echo",
        payload={"message": "forwarded"},
        routing_key="customer-123",
        origin_node_id="node-0",
        remaining_timeout_ms=900,
    )
    decoded = decode_forwarded_request(encoded)
    assert decoded.task.task_name == "echo"
    assert decoded.task.payload == {"message": "forwarded"}
    assert decoded.task.routing_key == "customer-123"
    assert decoded.origin_node_id == "node-0"
    assert decoded.remaining_timeout_ms == 900
