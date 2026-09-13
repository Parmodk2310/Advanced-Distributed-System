from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ErrorCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ERROR_CODE_UNSPECIFIED: _ClassVar[ErrorCode]
    UNKNOWN_TASK: _ClassVar[ErrorCode]
    INVALID_REQUEST: _ClassVar[ErrorCode]
    INTERNAL_ERROR: _ClassVar[ErrorCode]
    TIMEOUT: _ClassVar[ErrorCode]
    OVERLOADED: _ClassVar[ErrorCode]
    RATE_LIMITED: _ClassVar[ErrorCode]
    NO_ROUTE: _ClassVar[ErrorCode]
    PEER_UNAVAILABLE: _ClassVar[ErrorCode]

class MemberStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MEMBER_STATUS_UNSPECIFIED: _ClassVar[MemberStatus]
    ALIVE: _ClassVar[MemberStatus]
    SUSPECT: _ClassVar[MemberStatus]
    DEAD: _ClassVar[MemberStatus]
ERROR_CODE_UNSPECIFIED: ErrorCode
UNKNOWN_TASK: ErrorCode
INVALID_REQUEST: ErrorCode
INTERNAL_ERROR: ErrorCode
TIMEOUT: ErrorCode
OVERLOADED: ErrorCode
RATE_LIMITED: ErrorCode
NO_ROUTE: ErrorCode
PEER_UNAVAILABLE: ErrorCode
MEMBER_STATUS_UNSPECIFIED: MemberStatus
ALIVE: MemberStatus
SUSPECT: MemberStatus
DEAD: MemberStatus

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
    __slots__ = ("task_name", "payload_json", "routing_key")
    TASK_NAME_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    ROUTING_KEY_FIELD_NUMBER: _ClassVar[int]
    task_name: str
    payload_json: bytes
    routing_key: str
    def __init__(self, task_name: _Optional[str] = ..., payload_json: _Optional[bytes] = ..., routing_key: _Optional[str] = ...) -> None: ...

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

class ClusterMember(_message.Message):
    __slots__ = ("node_id", "host", "port", "status", "incarnation")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    HOST_FIELD_NUMBER: _ClassVar[int]
    PORT_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    INCARNATION_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    host: str
    port: int
    status: MemberStatus
    incarnation: int
    def __init__(self, node_id: _Optional[str] = ..., host: _Optional[str] = ..., port: _Optional[int] = ..., status: _Optional[_Union[MemberStatus, str]] = ..., incarnation: _Optional[int] = ...) -> None: ...

class JoinRequest(_message.Message):
    __slots__ = ("member",)
    MEMBER_FIELD_NUMBER: _ClassVar[int]
    member: ClusterMember
    def __init__(self, member: _Optional[_Union[ClusterMember, _Mapping]] = ...) -> None: ...

class JoinResponse(_message.Message):
    __slots__ = ("members",)
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    members: _containers.RepeatedCompositeFieldContainer[ClusterMember]
    def __init__(self, members: _Optional[_Iterable[_Union[ClusterMember, _Mapping]]] = ...) -> None: ...

class Ping(_message.Message):
    __slots__ = ("gossip",)
    GOSSIP_FIELD_NUMBER: _ClassVar[int]
    gossip: _containers.RepeatedCompositeFieldContainer[ClusterMember]
    def __init__(self, gossip: _Optional[_Iterable[_Union[ClusterMember, _Mapping]]] = ...) -> None: ...

class Ack(_message.Message):
    __slots__ = ("success", "target_node_id", "gossip")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    TARGET_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    GOSSIP_FIELD_NUMBER: _ClassVar[int]
    success: bool
    target_node_id: str
    gossip: _containers.RepeatedCompositeFieldContainer[ClusterMember]
    def __init__(self, success: _Optional[bool] = ..., target_node_id: _Optional[str] = ..., gossip: _Optional[_Iterable[_Union[ClusterMember, _Mapping]]] = ...) -> None: ...

class PingRequest(_message.Message):
    __slots__ = ("target", "gossip")
    TARGET_FIELD_NUMBER: _ClassVar[int]
    GOSSIP_FIELD_NUMBER: _ClassVar[int]
    target: ClusterMember
    gossip: _containers.RepeatedCompositeFieldContainer[ClusterMember]
    def __init__(self, target: _Optional[_Union[ClusterMember, _Mapping]] = ..., gossip: _Optional[_Iterable[_Union[ClusterMember, _Mapping]]] = ...) -> None: ...

class Gossip(_message.Message):
    __slots__ = ("members",)
    MEMBERS_FIELD_NUMBER: _ClassVar[int]
    members: _containers.RepeatedCompositeFieldContainer[ClusterMember]
    def __init__(self, members: _Optional[_Iterable[_Union[ClusterMember, _Mapping]]] = ...) -> None: ...

class ForwardedTaskRequest(_message.Message):
    __slots__ = ("request", "origin_node_id", "remaining_timeout_ms")
    REQUEST_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    REMAINING_TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    request: TaskRequest
    origin_node_id: str
    remaining_timeout_ms: int
    def __init__(self, request: _Optional[_Union[TaskRequest, _Mapping]] = ..., origin_node_id: _Optional[str] = ..., remaining_timeout_ms: _Optional[int] = ...) -> None: ...
