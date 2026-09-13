from distsys.protocol.codec import decode_envelope, encode_envelope
from distsys.protocol.message import Message, MessageType


def test_message_round_trip():
    message = Message.new_request(
        sender_id="client-1",
        correlation_id="corr-123",
        payload=b"payload",
    )
    decoded = decode_envelope(message.msg_type, encode_envelope(message))
    assert decoded == message
    assert decoded.msg_type is MessageType.REQUEST


def test_phase3_message_type_numbers_preserve_protocol_compatibility():
    assert MessageType.REQUEST == 1
    assert MessageType.RESPONSE == 2
    assert MessageType.ERROR == 3
    assert MessageType.HEARTBEAT == 4
    assert MessageType.JOIN_REQUEST == 5
    assert MessageType.JOIN_RESPONSE == 6
    assert MessageType.PING == 7
    assert MessageType.ACK == 8
    assert MessageType.PING_REQ == 9
    assert MessageType.GOSSIP == 10
    assert MessageType.FORWARDED_REQUEST == 11


def test_new_request_accepts_explicit_message_type():
    message = Message.new_request(sender_id="node-0", payload=b"control", msg_type=MessageType.PING)
    assert message.msg_type is MessageType.PING
