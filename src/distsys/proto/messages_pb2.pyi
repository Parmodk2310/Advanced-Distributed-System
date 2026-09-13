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
    CAUSAL_UNAVAILABLE: _ClassVar[ErrorCode]
    REPLICATION_BACKPRESSURE: _ClassVar[ErrorCode]
    KEY_NOT_FOUND: _ClassVar[ErrorCode]
    PERSISTENCE_UNAVAILABLE: _ClassVar[ErrorCode]
    PERSISTENCE_BACKPRESSURE: _ClassVar[ErrorCode]
    RECOVERY_IN_PROGRESS: _ClassVar[ErrorCode]
    COORDINATION_UNAVAILABLE: _ClassVar[ErrorCode]
    TLS_AUTHENTICATION_FAILED: _ClassVar[ErrorCode]

class MemberStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MEMBER_STATUS_UNSPECIFIED: _ClassVar[MemberStatus]
    ALIVE: _ClassVar[MemberStatus]
    SUSPECT: _ClassVar[MemberStatus]
    DEAD: _ClassVar[MemberStatus]

class CrdtType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CRDT_TYPE_UNSPECIFIED: _ClassVar[CrdtType]
    GCOUNTER: _ClassVar[CrdtType]
    PNCOUNTER: _ClassVar[CrdtType]
    ORSET: _ClassVar[CrdtType]
    MVREGISTER: _ClassVar[CrdtType]
ERROR_CODE_UNSPECIFIED: ErrorCode
UNKNOWN_TASK: ErrorCode
INVALID_REQUEST: ErrorCode
INTERNAL_ERROR: ErrorCode
TIMEOUT: ErrorCode
OVERLOADED: ErrorCode
RATE_LIMITED: ErrorCode
NO_ROUTE: ErrorCode
PEER_UNAVAILABLE: ErrorCode
CAUSAL_UNAVAILABLE: ErrorCode
REPLICATION_BACKPRESSURE: ErrorCode
KEY_NOT_FOUND: ErrorCode
PERSISTENCE_UNAVAILABLE: ErrorCode
PERSISTENCE_BACKPRESSURE: ErrorCode
RECOVERY_IN_PROGRESS: ErrorCode
COORDINATION_UNAVAILABLE: ErrorCode
TLS_AUTHENTICATION_FAILED: ErrorCode
MEMBER_STATUS_UNSPECIFIED: MemberStatus
ALIVE: MemberStatus
SUSPECT: MemberStatus
DEAD: MemberStatus
CRDT_TYPE_UNSPECIFIED: CrdtType
GCOUNTER: CrdtType
PNCOUNTER: CrdtType
ORSET: CrdtType
MVREGISTER: CrdtType

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

class CausalActor(_message.Message):
    __slots__ = ("node_id", "incarnation")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    INCARNATION_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    incarnation: int
    def __init__(self, node_id: _Optional[str] = ..., incarnation: _Optional[int] = ...) -> None: ...

class Dot(_message.Message):
    __slots__ = ("actor", "counter")
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    COUNTER_FIELD_NUMBER: _ClassVar[int]
    actor: CausalActor
    counter: int
    def __init__(self, actor: _Optional[_Union[CausalActor, _Mapping]] = ..., counter: _Optional[int] = ...) -> None: ...

class VersionEntry(_message.Message):
    __slots__ = ("actor", "counter")
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    COUNTER_FIELD_NUMBER: _ClassVar[int]
    actor: CausalActor
    counter: int
    def __init__(self, actor: _Optional[_Union[CausalActor, _Mapping]] = ..., counter: _Optional[int] = ...) -> None: ...

class VersionVector(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[VersionEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[VersionEntry, _Mapping]]] = ...) -> None: ...

class CausalToken(_message.Message):
    __slots__ = ("version",)
    VERSION_FIELD_NUMBER: _ClassVar[int]
    version: VersionVector
    def __init__(self, version: _Optional[_Union[VersionVector, _Mapping]] = ...) -> None: ...

class GCounterComponent(_message.Message):
    __slots__ = ("actor", "value")
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    actor: CausalActor
    value: int
    def __init__(self, actor: _Optional[_Union[CausalActor, _Mapping]] = ..., value: _Optional[int] = ...) -> None: ...

class GCounterState(_message.Message):
    __slots__ = ("components",)
    COMPONENTS_FIELD_NUMBER: _ClassVar[int]
    components: _containers.RepeatedCompositeFieldContainer[GCounterComponent]
    def __init__(self, components: _Optional[_Iterable[_Union[GCounterComponent, _Mapping]]] = ...) -> None: ...

class PNCounterState(_message.Message):
    __slots__ = ("positive", "negative")
    POSITIVE_FIELD_NUMBER: _ClassVar[int]
    NEGATIVE_FIELD_NUMBER: _ClassVar[int]
    positive: GCounterState
    negative: GCounterState
    def __init__(self, positive: _Optional[_Union[GCounterState, _Mapping]] = ..., negative: _Optional[_Union[GCounterState, _Mapping]] = ...) -> None: ...

class ORSetAdd(_message.Message):
    __slots__ = ("element", "dots")
    ELEMENT_FIELD_NUMBER: _ClassVar[int]
    DOTS_FIELD_NUMBER: _ClassVar[int]
    element: str
    dots: _containers.RepeatedCompositeFieldContainer[Dot]
    def __init__(self, element: _Optional[str] = ..., dots: _Optional[_Iterable[_Union[Dot, _Mapping]]] = ...) -> None: ...

class ORSetState(_message.Message):
    __slots__ = ("adds", "removed")
    ADDS_FIELD_NUMBER: _ClassVar[int]
    REMOVED_FIELD_NUMBER: _ClassVar[int]
    adds: _containers.RepeatedCompositeFieldContainer[ORSetAdd]
    removed: _containers.RepeatedCompositeFieldContainer[Dot]
    def __init__(self, adds: _Optional[_Iterable[_Union[ORSetAdd, _Mapping]]] = ..., removed: _Optional[_Iterable[_Union[Dot, _Mapping]]] = ...) -> None: ...

class RegisterValue(_message.Message):
    __slots__ = ("dot", "value_json")
    DOT_FIELD_NUMBER: _ClassVar[int]
    VALUE_JSON_FIELD_NUMBER: _ClassVar[int]
    dot: Dot
    value_json: bytes
    def __init__(self, dot: _Optional[_Union[Dot, _Mapping]] = ..., value_json: _Optional[bytes] = ...) -> None: ...

class MVRegisterState(_message.Message):
    __slots__ = ("values", "superseded")
    VALUES_FIELD_NUMBER: _ClassVar[int]
    SUPERSEDED_FIELD_NUMBER: _ClassVar[int]
    values: _containers.RepeatedCompositeFieldContainer[RegisterValue]
    superseded: _containers.RepeatedCompositeFieldContainer[Dot]
    def __init__(self, values: _Optional[_Iterable[_Union[RegisterValue, _Mapping]]] = ..., superseded: _Optional[_Iterable[_Union[Dot, _Mapping]]] = ...) -> None: ...

class CrdtState(_message.Message):
    __slots__ = ("key", "crdt_type", "state_version", "causal_context", "gcounter", "pncounter", "orset", "mvregister")
    KEY_FIELD_NUMBER: _ClassVar[int]
    CRDT_TYPE_FIELD_NUMBER: _ClassVar[int]
    STATE_VERSION_FIELD_NUMBER: _ClassVar[int]
    CAUSAL_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    GCOUNTER_FIELD_NUMBER: _ClassVar[int]
    PNCOUNTER_FIELD_NUMBER: _ClassVar[int]
    ORSET_FIELD_NUMBER: _ClassVar[int]
    MVREGISTER_FIELD_NUMBER: _ClassVar[int]
    key: str
    crdt_type: CrdtType
    state_version: VersionVector
    causal_context: VersionVector
    gcounter: GCounterState
    pncounter: PNCounterState
    orset: ORSetState
    mvregister: MVRegisterState
    def __init__(self, key: _Optional[str] = ..., crdt_type: _Optional[_Union[CrdtType, str]] = ..., state_version: _Optional[_Union[VersionVector, _Mapping]] = ..., causal_context: _Optional[_Union[VersionVector, _Mapping]] = ..., gcounter: _Optional[_Union[GCounterState, _Mapping]] = ..., pncounter: _Optional[_Union[PNCounterState, _Mapping]] = ..., orset: _Optional[_Union[ORSetState, _Mapping]] = ..., mvregister: _Optional[_Union[MVRegisterState, _Mapping]] = ...) -> None: ...

class IncrementMutation(_message.Message):
    __slots__ = ("amount",)
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    amount: int
    def __init__(self, amount: _Optional[int] = ...) -> None: ...

class DecrementMutation(_message.Message):
    __slots__ = ("amount",)
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    amount: int
    def __init__(self, amount: _Optional[int] = ...) -> None: ...

class SetAddMutation(_message.Message):
    __slots__ = ("element",)
    ELEMENT_FIELD_NUMBER: _ClassVar[int]
    element: str
    def __init__(self, element: _Optional[str] = ...) -> None: ...

class SetRemoveMutation(_message.Message):
    __slots__ = ("element",)
    ELEMENT_FIELD_NUMBER: _ClassVar[int]
    element: str
    def __init__(self, element: _Optional[str] = ...) -> None: ...

class RegisterWriteMutation(_message.Message):
    __slots__ = ("value_json",)
    VALUE_JSON_FIELD_NUMBER: _ClassVar[int]
    value_json: bytes
    def __init__(self, value_json: _Optional[bytes] = ...) -> None: ...

class CrdtMutationRequest(_message.Message):
    __slots__ = ("key", "crdt_type", "causal_token", "forwarded", "origin_node_id", "remaining_timeout_ms", "increment", "decrement", "set_add", "set_remove", "register_write")
    KEY_FIELD_NUMBER: _ClassVar[int]
    CRDT_TYPE_FIELD_NUMBER: _ClassVar[int]
    CAUSAL_TOKEN_FIELD_NUMBER: _ClassVar[int]
    FORWARDED_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    REMAINING_TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    INCREMENT_FIELD_NUMBER: _ClassVar[int]
    DECREMENT_FIELD_NUMBER: _ClassVar[int]
    SET_ADD_FIELD_NUMBER: _ClassVar[int]
    SET_REMOVE_FIELD_NUMBER: _ClassVar[int]
    REGISTER_WRITE_FIELD_NUMBER: _ClassVar[int]
    key: str
    crdt_type: CrdtType
    causal_token: CausalToken
    forwarded: bool
    origin_node_id: str
    remaining_timeout_ms: int
    increment: IncrementMutation
    decrement: DecrementMutation
    set_add: SetAddMutation
    set_remove: SetRemoveMutation
    register_write: RegisterWriteMutation
    def __init__(self, key: _Optional[str] = ..., crdt_type: _Optional[_Union[CrdtType, str]] = ..., causal_token: _Optional[_Union[CausalToken, _Mapping]] = ..., forwarded: _Optional[bool] = ..., origin_node_id: _Optional[str] = ..., remaining_timeout_ms: _Optional[int] = ..., increment: _Optional[_Union[IncrementMutation, _Mapping]] = ..., decrement: _Optional[_Union[DecrementMutation, _Mapping]] = ..., set_add: _Optional[_Union[SetAddMutation, _Mapping]] = ..., set_remove: _Optional[_Union[SetRemoveMutation, _Mapping]] = ..., register_write: _Optional[_Union[RegisterWriteMutation, _Mapping]] = ...) -> None: ...

class CrdtReadRequest(_message.Message):
    __slots__ = ("key", "causal_token", "forwarded", "origin_node_id", "remaining_timeout_ms")
    KEY_FIELD_NUMBER: _ClassVar[int]
    CAUSAL_TOKEN_FIELD_NUMBER: _ClassVar[int]
    FORWARDED_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    REMAINING_TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    key: str
    causal_token: CausalToken
    forwarded: bool
    origin_node_id: str
    remaining_timeout_ms: int
    def __init__(self, key: _Optional[str] = ..., causal_token: _Optional[_Union[CausalToken, _Mapping]] = ..., forwarded: _Optional[bool] = ..., origin_node_id: _Optional[str] = ..., remaining_timeout_ms: _Optional[int] = ...) -> None: ...

class CrdtReplicate(_message.Message):
    __slots__ = ("state",)
    STATE_FIELD_NUMBER: _ClassVar[int]
    state: CrdtState
    def __init__(self, state: _Optional[_Union[CrdtState, _Mapping]] = ...) -> None: ...

class CrdtFetch(_message.Message):
    __slots__ = ("key",)
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: _Optional[str] = ...) -> None: ...

class CrdtDigestEntry(_message.Message):
    __slots__ = ("key", "crdt_type", "state_version", "causal_context")
    KEY_FIELD_NUMBER: _ClassVar[int]
    CRDT_TYPE_FIELD_NUMBER: _ClassVar[int]
    STATE_VERSION_FIELD_NUMBER: _ClassVar[int]
    CAUSAL_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    key: str
    crdt_type: CrdtType
    state_version: VersionVector
    causal_context: VersionVector
    def __init__(self, key: _Optional[str] = ..., crdt_type: _Optional[_Union[CrdtType, str]] = ..., state_version: _Optional[_Union[VersionVector, _Mapping]] = ..., causal_context: _Optional[_Union[VersionVector, _Mapping]] = ...) -> None: ...

class CrdtDigest(_message.Message):
    __slots__ = ("requester_node_id", "entries", "batch_size")
    REQUESTER_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    BATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    requester_node_id: str
    entries: _containers.RepeatedCompositeFieldContainer[CrdtDigestEntry]
    batch_size: int
    def __init__(self, requester_node_id: _Optional[str] = ..., entries: _Optional[_Iterable[_Union[CrdtDigestEntry, _Mapping]]] = ..., batch_size: _Optional[int] = ...) -> None: ...

class CrdtDigestResponse(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[CrdtDigestEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[CrdtDigestEntry, _Mapping]]] = ...) -> None: ...

class CrdtResponse(_message.Message):
    __slots__ = ("success", "crdt_type", "value_json", "causal_token", "served_by", "repair_performed", "error", "state", "peer_frontier")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CRDT_TYPE_FIELD_NUMBER: _ClassVar[int]
    VALUE_JSON_FIELD_NUMBER: _ClassVar[int]
    CAUSAL_TOKEN_FIELD_NUMBER: _ClassVar[int]
    SERVED_BY_FIELD_NUMBER: _ClassVar[int]
    REPAIR_PERFORMED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    PEER_FRONTIER_FIELD_NUMBER: _ClassVar[int]
    success: bool
    crdt_type: CrdtType
    value_json: bytes
    causal_token: CausalToken
    served_by: str
    repair_performed: bool
    error: Error
    state: CrdtState
    peer_frontier: VersionVector
    def __init__(self, success: _Optional[bool] = ..., crdt_type: _Optional[_Union[CrdtType, str]] = ..., value_json: _Optional[bytes] = ..., causal_token: _Optional[_Union[CausalToken, _Mapping]] = ..., served_by: _Optional[str] = ..., repair_performed: _Optional[bool] = ..., error: _Optional[_Union[Error, _Mapping]] = ..., state: _Optional[_Union[CrdtState, _Mapping]] = ..., peer_frontier: _Optional[_Union[VersionVector, _Mapping]] = ...) -> None: ...
