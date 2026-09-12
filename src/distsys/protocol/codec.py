"""Protobuf and JSON application codec."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from google.protobuf.message import DecodeError as ProtobufDecodeError

from distsys.proto import messages_pb2
from distsys.protocol.errors import DecodeError
from distsys.protocol.message import Message, MessageType


@dataclass(slots=True, frozen=True)
class TaskResponseData:
    success: bool
    result: Any | None
    error_code: messages_pb2.ErrorCode
    error_message: str
    processing_time_us: int


def encode_envelope(message: Message) -> bytes:
    envelope = messages_pb2.Envelope(
        sender_id=message.sender_id,
        correlation_id=message.correlation_id,
        timestamp_ms=message.timestamp_ms,
        ttl=message.ttl,
        payload=message.payload,
    )
    return envelope.SerializeToString()


def decode_envelope(msg_type: MessageType, data: bytes) -> Message:
    envelope = messages_pb2.Envelope()
    try:
        envelope.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid protobuf envelope") from exc

    if not envelope.sender_id:
        raise DecodeError("sender_id is required")
    if not envelope.correlation_id:
        raise DecodeError("correlation_id is required")

    return Message(
        msg_type=msg_type,
        sender_id=envelope.sender_id,
        correlation_id=envelope.correlation_id,
        timestamp_ms=envelope.timestamp_ms,
        ttl=envelope.ttl,
        payload=envelope.payload,
    )


def _json_dump(value: Any) -> bytes:
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DecodeError(f"value is not JSON serializable: {exc}") from exc


def _json_load(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8")) if data else None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecodeError("invalid JSON application payload") from exc


def encode_task_request(task_name: str, payload: Any) -> bytes:
    if not task_name:
        raise DecodeError("task_name is required")
    request = messages_pb2.TaskRequest(task_name=task_name, payload_json=_json_dump(payload))
    return request.SerializeToString()


def decode_task_request(data: bytes) -> tuple[str, Any]:
    request = messages_pb2.TaskRequest()
    try:
        request.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid TaskRequest protobuf") from exc
    if not request.task_name:
        raise DecodeError("task_name is required")
    return request.task_name, _json_load(request.payload_json)


def encode_task_response(
    *,
    success: bool,
    result: Any | None = None,
    error_code: messages_pb2.ErrorCode = messages_pb2.ERROR_CODE_UNSPECIFIED,
    error_message: str = "",
    processing_time_us: int = 0,
) -> bytes:
    response = messages_pb2.TaskResponse(
        success=success,
        result_json=_json_dump(result) if success else b"",
        processing_time_us=processing_time_us,
    )
    if not success:
        response.error.code = error_code
        response.error.message = error_message
    return response.SerializeToString()


def decode_task_response(data: bytes) -> TaskResponseData:
    response = messages_pb2.TaskResponse()
    try:
        response.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid TaskResponse protobuf") from exc
    return TaskResponseData(
        success=response.success,
        result=_json_load(response.result_json) if response.success else None,
        error_code=response.error.code,
        error_message=response.error.message,
        processing_time_us=response.processing_time_us,
    )
