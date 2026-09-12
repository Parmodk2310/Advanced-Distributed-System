from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ErrorCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ERROR_CODE_UNSPECIFIED: _ClassVar[ErrorCode]
    UNKNOWN_TASK: _ClassVar[ErrorCode]
    INVALID_REQUEST: _ClassVar[ErrorCode]
    INTERNAL_ERROR: _ClassVar[ErrorCode]
    TIMEOUT: _ClassVar[ErrorCode]
ERROR_CODE_UNSPECIFIED: ErrorCode
UNKNOWN_TASK: ErrorCode
INVALID_REQUEST: ErrorCode
INTERNAL_ERROR: ErrorCode
TIMEOUT: ErrorCode

class Envelope(_message.Message):
    __slots__ = ("sender_id", "correlation_id", "timestamp_ms", "ttl", "payload")
    SENDER_ID_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_MS_FIELD_NUMBER: _ClassVar[int]
    TTL_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    sender_id: str
    correlation_id: str
    timestamp_ms: int
    ttl: int
    payload: bytes
    def __init__(self, sender_id: _Optional[str] = ..., correlation_id: _Optional[str] = ..., timestamp_ms: _Optional[int] = ..., ttl: _Optional[int] = ..., payload: _Optional[bytes] = ...) -> None: ...

class TaskRequest(_message.Message):
    __slots__ = ("task_name", "payload_json")
    TASK_NAME_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    task_name: str
    payload_json: bytes
    def __init__(self, task_name: _Optional[str] = ..., payload_json: _Optional[bytes] = ...) -> None: ...

class Error(_message.Message):
    __slots__ = ("code", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: ErrorCode
    message: str
    def __init__(self, code: _Optional[_Union[ErrorCode, str]] = ..., message: _Optional[str] = ...) -> None: ...

class TaskResponse(_message.Message):
    __slots__ = ("success", "result_json", "error", "processing_time_us")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    RESULT_JSON_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    PROCESSING_TIME_US_FIELD_NUMBER: _ClassVar[int]
    success: bool
    result_json: bytes
    error: Error
    processing_time_us: int
    def __init__(self, success: _Optional[bool] = ..., result_json: _Optional[bytes] = ..., error: _Optional[_Union[Error, _Mapping]] = ..., processing_time_us: _Optional[int] = ...) -> None: ...
