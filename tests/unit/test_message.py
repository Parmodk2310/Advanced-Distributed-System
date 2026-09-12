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
