"""Typed Protobuf codecs for Phase-4 causal CRDT traffic."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

from google.protobuf.message import DecodeError as ProtobufDecodeError

from distsys.causal import CausalActor, CausalToken, Dot, VersionVector
from distsys.crdt import CrdtType, GCounter, MVRegister, ORSet, PNCounter
from distsys.proto import messages_pb2
from distsys.protocol.errors import DecodeError
from distsys.replication.digest import CrdtDigestEntry
from distsys.storage import CrdtState, StoredCrdtEntry


def _json_dump(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DecodeError(f"value is not JSON serializable: {exc}") from exc


def _json_load(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8")) if data else None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecodeError("invalid JSON payload") from exc


def actor_to_proto(actor: CausalActor):
    return messages_pb2.CausalActor(node_id=actor.node_id, incarnation=actor.incarnation)


def actor_from_proto(proto) -> CausalActor:
    return CausalActor(proto.node_id, proto.incarnation)


def dot_to_proto(dot: Dot):
    msg = messages_pb2.Dot(counter=dot.counter)
    msg.actor.CopyFrom(actor_to_proto(dot.actor))
    return msg


def dot_from_proto(proto) -> Dot:
    return Dot(actor_from_proto(proto.actor), proto.counter)


def version_to_proto(vector: VersionVector):
    msg = messages_pb2.VersionVector()
    for actor, counter in vector.items():
        item = msg.entries.add()
        item.actor.CopyFrom(actor_to_proto(actor))
        item.counter = counter
    return msg


def version_from_proto(proto) -> VersionVector:
    return VersionVector({actor_from_proto(item.actor): item.counter for item in proto.entries})


def token_to_proto(token: CausalToken):
    msg = messages_pb2.CausalToken()
    msg.version.CopyFrom(version_to_proto(token.version))
    return msg


def token_from_proto(proto) -> CausalToken:
    return CausalToken(version_from_proto(proto.version))


def encode_token(token: CausalToken) -> bytes:
    return token_to_proto(token).SerializeToString(deterministic=True)


def decode_token(data: bytes) -> CausalToken:
    msg = messages_pb2.CausalToken()
    try:
        msg.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid CausalToken protobuf") from exc
    return token_from_proto(msg)


def _type_to_proto(crdt_type: CrdtType) -> messages_pb2.CrdtType:
    return {
        CrdtType.GCOUNTER: messages_pb2.GCOUNTER,
        CrdtType.PNCOUNTER: messages_pb2.PNCOUNTER,
        CrdtType.ORSET: messages_pb2.ORSET,
        CrdtType.MVREGISTER: messages_pb2.MVREGISTER,
    }[crdt_type]


def _type_from_proto(raw: messages_pb2.CrdtType) -> CrdtType:
    if raw == messages_pb2.GCOUNTER:
        return CrdtType.GCOUNTER
    if raw == messages_pb2.PNCOUNTER:
        return CrdtType.PNCOUNTER
    if raw == messages_pb2.ORSET:
        return CrdtType.ORSET
    if raw == messages_pb2.MVREGISTER:
        return CrdtType.MVREGISTER
    raise DecodeError(f"invalid CRDT type: {raw}")


def _gcounter_to_proto(state: GCounter):
    msg = messages_pb2.GCounterState()
    for actor, value in state.components():
        item = msg.components.add()
        item.actor.CopyFrom(actor_to_proto(actor))
        item.value = value
    return msg


def _gcounter_from_proto(msg) -> GCounter:
    return GCounter({actor_from_proto(item.actor): item.value for item in msg.components})


def state_to_proto(entry: StoredCrdtEntry):
    msg = messages_pb2.CrdtState(key=entry.key, crdt_type=_type_to_proto(entry.crdt_type))
    msg.state_version.CopyFrom(version_to_proto(entry.state_version))
    msg.causal_context.CopyFrom(version_to_proto(entry.causal_context))

    if entry.crdt_type is CrdtType.GCOUNTER:
        assert isinstance(entry.state, GCounter)
        msg.gcounter.CopyFrom(_gcounter_to_proto(entry.state))
    elif entry.crdt_type is CrdtType.PNCOUNTER:
        assert isinstance(entry.state, PNCounter)
        msg.pncounter.positive.CopyFrom(_gcounter_to_proto(entry.state.positive))
        msg.pncounter.negative.CopyFrom(_gcounter_to_proto(entry.state.negative))
    elif entry.crdt_type is CrdtType.ORSET:
        assert isinstance(entry.state, ORSet)
        for element, dots in entry.state.additions():
            add = msg.orset.adds.add()
            add.element = element
            for dot in sorted(dots):
                add.dots.add().CopyFrom(dot_to_proto(dot))
        for dot in sorted(entry.state.removed()):
            msg.orset.removed.add().CopyFrom(dot_to_proto(dot))
    elif entry.crdt_type is CrdtType.MVREGISTER:
        assert isinstance(entry.state, MVRegister)
        for dot, encoded in entry.state.entries():
            item = msg.mvregister.values.add()
            item.dot.CopyFrom(dot_to_proto(dot))
            item.value_json = encoded.encode("utf-8")
        for dot in sorted(entry.state.superseded()):
            msg.mvregister.superseded.add().CopyFrom(dot_to_proto(dot))
    return msg


def state_from_proto(msg) -> StoredCrdtEntry:
    if not msg.key:
        raise DecodeError("CRDT state key is required")
    crdt_type = _type_from_proto(msg.crdt_type)
    which = msg.WhichOneof("state")
    state: CrdtState
    if crdt_type is CrdtType.GCOUNTER and which == "gcounter":
        state = _gcounter_from_proto(msg.gcounter)
    elif crdt_type is CrdtType.PNCOUNTER and which == "pncounter":
        state = PNCounter(
            _gcounter_from_proto(msg.pncounter.positive),
            _gcounter_from_proto(msg.pncounter.negative),
        )
    elif crdt_type is CrdtType.ORSET and which == "orset":
        state = ORSet(
            {
                item.element: frozenset(dot_from_proto(dot) for dot in item.dots)
                for item in msg.orset.adds
            },
            frozenset(dot_from_proto(dot) for dot in msg.orset.removed),
        )
    elif crdt_type is CrdtType.MVREGISTER and which == "mvregister":
        values: dict[Dot, str] = {}
        for item in msg.mvregister.values:
            try:
                encoded = item.value_json.decode("utf-8")
                json.loads(encoded)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DecodeError("invalid MVRegister JSON payload") from exc
            values[dot_from_proto(item.dot)] = encoded
        state = MVRegister(
            values,
            frozenset(dot_from_proto(dot) for dot in msg.mvregister.superseded),
        )
    else:
        raise DecodeError("CRDT type/state mismatch")
    return StoredCrdtEntry(
        msg.key,
        crdt_type,
        state,
        version_from_proto(msg.state_version),
        version_from_proto(msg.causal_context),
    )


def digest_to_proto(entry: CrdtDigestEntry):
    msg = messages_pb2.CrdtDigestEntry(key=entry.key, crdt_type=_type_to_proto(entry.crdt_type))
    msg.state_version.CopyFrom(version_to_proto(entry.state_version))
    msg.causal_context.CopyFrom(version_to_proto(entry.causal_context))
    return msg


def digest_from_proto(msg) -> CrdtDigestEntry:
    return CrdtDigestEntry(
        msg.key,
        _type_from_proto(msg.crdt_type),
        version_from_proto(msg.state_version),
        version_from_proto(msg.causal_context),
    )


@dataclass(frozen=True, slots=True)
class CrdtMutationData:
    key: str
    crdt_type: CrdtType
    operation: str
    value: Any = None
    amount: int = 0
    causal_token: CausalToken = field(default_factory=CausalToken.empty)
    forwarded: bool = False
    origin_node_id: str = ""
    remaining_timeout_ms: int = 0


@dataclass(frozen=True, slots=True)
class CrdtReadData:
    key: str
    causal_token: CausalToken = field(default_factory=CausalToken.empty)
    forwarded: bool = False
    origin_node_id: str = ""
    remaining_timeout_ms: int = 0


@dataclass(frozen=True, slots=True)
class CrdtResponseData:
    success: bool
    crdt_type: CrdtType | None = None
    value: Any = None
    causal_token: CausalToken = field(default_factory=CausalToken.empty)
    served_by: str = ""
    repair_performed: bool = False
    error_code: int = 0
    error_message: str = ""
    state: StoredCrdtEntry | None = None
    peer_frontier: VersionVector = field(default_factory=VersionVector)


def encode_mutation_request(req: CrdtMutationData) -> bytes:
    if not req.key:
        raise DecodeError("CRDT key is required")
    msg = messages_pb2.CrdtMutationRequest(
        key=req.key,
        crdt_type=_type_to_proto(req.crdt_type),
        forwarded=req.forwarded,
        origin_node_id=req.origin_node_id,
        remaining_timeout_ms=req.remaining_timeout_ms,
    )
    msg.causal_token.CopyFrom(token_to_proto(req.causal_token))
    if req.operation == "increment":
        if req.amount < 1:
            raise DecodeError("increment amount must be >= 1")
        msg.increment.amount = req.amount
    elif req.operation == "decrement":
        if req.amount < 1:
            raise DecodeError("decrement amount must be >= 1")
        msg.decrement.amount = req.amount
    elif req.operation == "add":
        if not isinstance(req.value, str):
            raise DecodeError("ORSet add value must be a string")
        msg.set_add.element = req.value
    elif req.operation == "remove":
        if not isinstance(req.value, str):
            raise DecodeError("ORSet remove value must be a string")
        msg.set_remove.element = req.value
    elif req.operation == "write":
        msg.register_write.value_json = _json_dump(req.value)
    else:
        raise DecodeError(f"unsupported mutation operation: {req.operation}")
    return msg.SerializeToString(deterministic=True)


def decode_mutation_request(data: bytes) -> CrdtMutationData:
    msg = messages_pb2.CrdtMutationRequest()
    try:
        msg.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid CrdtMutationRequest protobuf") from exc
    if not msg.key:
        raise DecodeError("CRDT key is required")
    crdt_type = _type_from_proto(msg.crdt_type)
    which = msg.WhichOneof("mutation")
    if which == "increment":
        operation, value, amount = "increment", None, msg.increment.amount
    elif which == "decrement":
        operation, value, amount = "decrement", None, msg.decrement.amount
    elif which == "set_add":
        operation, value, amount = "add", msg.set_add.element, 0
    elif which == "set_remove":
        operation, value, amount = "remove", msg.set_remove.element, 0
    elif which == "register_write":
        operation, value, amount = "write", _json_load(msg.register_write.value_json), 0
    else:
        raise DecodeError("mutation is required")
    return CrdtMutationData(
        msg.key,
        crdt_type,
        operation,
        value,
        amount,
        token_from_proto(msg.causal_token),
        msg.forwarded,
        msg.origin_node_id,
        msg.remaining_timeout_ms,
    )


def encode_read_request(req: CrdtReadData) -> bytes:
    if not req.key:
        raise DecodeError("CRDT key is required")
    msg = messages_pb2.CrdtReadRequest(
        key=req.key,
        forwarded=req.forwarded,
        origin_node_id=req.origin_node_id,
        remaining_timeout_ms=req.remaining_timeout_ms,
    )
    msg.causal_token.CopyFrom(token_to_proto(req.causal_token))
    return msg.SerializeToString(deterministic=True)


def decode_read_request(data: bytes) -> CrdtReadData:
    msg = messages_pb2.CrdtReadRequest()
    try:
        msg.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid CrdtReadRequest protobuf") from exc
    if not msg.key:
        raise DecodeError("CRDT key is required")
    return CrdtReadData(
        msg.key,
        token_from_proto(msg.causal_token),
        msg.forwarded,
        msg.origin_node_id,
        msg.remaining_timeout_ms,
    )


def encode_crdt_response(response: CrdtResponseData) -> bytes:
    msg = messages_pb2.CrdtResponse(success=response.success)
    if response.crdt_type is not None:
        msg.crdt_type = _type_to_proto(response.crdt_type)
    if response.success:
        msg.value_json = _json_dump(response.value)
        msg.causal_token.CopyFrom(token_to_proto(response.causal_token))
        msg.served_by = response.served_by
        msg.repair_performed = response.repair_performed
        if response.state is not None:
            msg.state.CopyFrom(state_to_proto(response.state))
        msg.peer_frontier.CopyFrom(version_to_proto(response.peer_frontier))
    else:
        msg.error.code = cast(messages_pb2.ErrorCode, response.error_code)
        msg.error.message = response.error_message
    return msg.SerializeToString(deterministic=True)


def decode_crdt_response(data: bytes) -> CrdtResponseData:
    msg = messages_pb2.CrdtResponse()
    try:
        msg.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid CrdtResponse protobuf") from exc
    return CrdtResponseData(
        success=msg.success,
        crdt_type=_type_from_proto(msg.crdt_type) if msg.success and msg.crdt_type else None,
        value=_json_load(msg.value_json) if msg.success else None,
        causal_token=token_from_proto(msg.causal_token) if msg.success else CausalToken.empty(),
        served_by=msg.served_by,
        repair_performed=msg.repair_performed,
        error_code=msg.error.code,
        error_message=msg.error.message,
        state=state_from_proto(msg.state) if msg.success and msg.HasField("state") else None,
        peer_frontier=(
            version_from_proto(msg.peer_frontier)
            if msg.success and msg.HasField("peer_frontier")
            else VersionVector()
        ),
    )


def encode_replication(entry: StoredCrdtEntry) -> bytes:
    msg = messages_pb2.CrdtReplicate()
    msg.state.CopyFrom(state_to_proto(entry))
    return msg.SerializeToString(deterministic=True)


def decode_replication(data: bytes) -> StoredCrdtEntry:
    msg = messages_pb2.CrdtReplicate()
    try:
        msg.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid CrdtReplicate protobuf") from exc
    return state_from_proto(msg.state)


def encode_fetch_request(key: str) -> bytes:
    if not key:
        raise DecodeError("CRDT key is required")
    return messages_pb2.CrdtFetch(key=key).SerializeToString(deterministic=True)


def decode_fetch_request(data: bytes) -> str:
    msg = messages_pb2.CrdtFetch()
    try:
        msg.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid CrdtFetch protobuf") from exc
    if not msg.key:
        raise DecodeError("CRDT key is required")
    return msg.key


def encode_digest_request(
    requester_node_id: str,
    entries: tuple[CrdtDigestEntry, ...],
    *,
    batch_size: int,
) -> bytes:
    msg = messages_pb2.CrdtDigest(requester_node_id=requester_node_id, batch_size=batch_size)
    for entry in entries:
        msg.entries.add().CopyFrom(digest_to_proto(entry))
    return msg.SerializeToString(deterministic=True)


def decode_digest_request(data: bytes) -> tuple[str, tuple[CrdtDigestEntry, ...], int]:
    msg = messages_pb2.CrdtDigest()
    try:
        msg.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid CrdtDigest protobuf") from exc
    return (
        msg.requester_node_id,
        tuple(digest_from_proto(item) for item in msg.entries),
        msg.batch_size,
    )


def encode_digest_response(entries: tuple[CrdtDigestEntry, ...]) -> bytes:
    msg = messages_pb2.CrdtDigestResponse()
    for entry in entries:
        msg.entries.add().CopyFrom(digest_to_proto(entry))
    return msg.SerializeToString(deterministic=True)


def decode_digest_response(data: bytes) -> tuple[CrdtDigestEntry, ...]:
    msg = messages_pb2.CrdtDigestResponse()
    try:
        msg.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid CrdtDigestResponse protobuf") from exc
    return tuple(digest_from_proto(item) for item in msg.entries)
