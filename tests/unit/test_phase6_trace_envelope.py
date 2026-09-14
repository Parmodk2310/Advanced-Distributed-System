from distsys.proto import messages_pb2
from distsys.protocol.codec import decode_envelope, encode_envelope
from distsys.protocol.message import Message, MessageType


def test_trace_context_round_trips_in_optional_envelope_fields():
    message = Message.new_request(
        sender_id="node-0",
        payload=b"x",
        traceparent="00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        tracestate="vendor=value",
    )
    decoded = decode_envelope(MessageType.REQUEST, encode_envelope(message))
    assert decoded.traceparent == message.traceparent
    assert decoded.tracestate == message.tracestate


def test_phase5_envelope_without_trace_fields_remains_valid():
    legacy = messages_pb2.Envelope(
        sender_id="node-0",
        correlation_id="legacy",
        timestamp_ms=1,
        ttl=8,
        payload=b"x",
    ).SerializeToString()
    decoded = decode_envelope(MessageType.REQUEST, legacy)
    assert decoded.traceparent == ""
    assert decoded.tracestate == ""
