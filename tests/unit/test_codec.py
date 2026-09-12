import pytest

from distsys.proto import messages_pb2
from distsys.protocol.codec import (
    decode_task_request,
    decode_task_response,
    encode_task_request,
    encode_task_response,
)


def test_task_request_round_trip():
    payload = {"message": "hello", "count": 3}
    task, decoded = decode_task_request(encode_task_request("echo", payload))
    assert task == "echo"
    assert decoded == payload


def test_task_response_success_round_trip():
    encoded = encode_task_response(success=True, result={"ok": True}, processing_time_us=12)
    decoded = decode_task_response(encoded)
    assert decoded.success is True
    assert decoded.result == {"ok": True}
    assert decoded.processing_time_us == 12


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
