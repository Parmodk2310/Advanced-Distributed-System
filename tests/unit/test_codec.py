import pytest

from distsys.proto import messages_pb2
from distsys.protocol.codec import (
    decode_task_request,
    decode_task_response,
    encode_task_request,
    encode_task_response,
)
from distsys.protocol.errors import DecodeError


def test_task_request_round_trip():
    encoded = encode_task_request("echo", {"message": "hello"})
    decoded = decode_task_request(encoded)
    assert decoded.task_name == "echo"
    assert decoded.payload == {"message": "hello"}
    assert decoded.routing_key == ""


def test_task_request_round_trip_with_routing_key():
    decoded = decode_task_request(
        encode_task_request(
            "echo",
            {"message": "hello"},
            routing_key="customer-123",
        )
    )
    assert decoded.task_name == "echo"
    assert decoded.payload == {"message": "hello"}
    assert decoded.routing_key == "customer-123"


def test_task_response_success_round_trip():
    encoded = encode_task_response(
        success=True,
        result={"ok": True},
        processing_time_us=123,
    )
    decoded = decode_task_response(encoded)
    assert decoded.success is True
    assert decoded.result == {"ok": True}
    assert decoded.processing_time_us == 123


def test_task_response_error_round_trip():
    encoded = encode_task_response(
        success=False,
        error_code=messages_pb2.UNKNOWN_TASK,
        error_message="unknown task",
    )
    decoded = decode_task_response(encoded)
    assert decoded.success is False
    assert decoded.error_code == messages_pb2.UNKNOWN_TASK
    assert decoded.error_message == "unknown task"


def test_invalid_task_request_raises_decode_error():
    with pytest.raises(DecodeError):
        decode_task_request(b"not-protobuf")
