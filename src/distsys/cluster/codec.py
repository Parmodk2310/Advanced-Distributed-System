"""Protobuf codecs for cluster control and forwarded-task messages."""

from __future__ import annotations

from dataclasses import dataclass

from google.protobuf.message import DecodeError as ProtobufDecodeError

from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.proto import messages_pb2
from distsys.protocol.codec import TaskRequestData, decode_task_request, encode_task_request
from distsys.protocol.errors import DecodeError


@dataclass(slots=True, frozen=True)
class AckData:
    success: bool
    target_node_id: str
    gossip: tuple[ClusterMember, ...]


@dataclass(slots=True, frozen=True)
class ForwardedTaskData:
    task: TaskRequestData
    origin_node_id: str
    remaining_timeout_ms: int


def member_to_proto(member: ClusterMember) -> messages_pb2.ClusterMember:
    status_map: dict[MemberStatus, messages_pb2.MemberStatus] = {
        MemberStatus.ALIVE: messages_pb2.ALIVE,
        MemberStatus.SUSPECT: messages_pb2.SUSPECT,
        MemberStatus.DEAD: messages_pb2.DEAD,
    }
    return messages_pb2.ClusterMember(
        node_id=member.node_id,
        host=member.host,
        port=member.port,
        status=status_map[member.status],
        incarnation=member.incarnation,
    )


def member_from_proto(value) -> ClusterMember:
    if not value.node_id or not value.host:
        raise DecodeError("cluster member node_id and host are required")
    try:
        status = MemberStatus(value.status)
        return ClusterMember(
            value.node_id,
            value.host,
            value.port,
            status,
            value.incarnation,
        )
    except ValueError as exc:
        raise DecodeError(str(exc)) from exc


def _parse(message, data: bytes, label: str):
    try:
        message.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError(f"invalid {label} protobuf") from exc
    return message


def encode_join_request(member: ClusterMember) -> bytes:
    return messages_pb2.JoinRequest(member=member_to_proto(member)).SerializeToString()


def decode_join_request(data: bytes) -> ClusterMember:
    value = _parse(messages_pb2.JoinRequest(), data, "JoinRequest")
    return member_from_proto(value.member)


def encode_join_response(members: tuple[ClusterMember, ...]) -> bytes:
    value = messages_pb2.JoinResponse()
    value.members.extend(member_to_proto(member) for member in members)
    return value.SerializeToString()


def decode_join_response(data: bytes) -> tuple[ClusterMember, ...]:
    value = _parse(messages_pb2.JoinResponse(), data, "JoinResponse")
    return tuple(member_from_proto(member) for member in value.members)


def encode_ping(gossip: tuple[ClusterMember, ...]) -> bytes:
    value = messages_pb2.Ping()
    value.gossip.extend(member_to_proto(member) for member in gossip)
    return value.SerializeToString()


def decode_ping(data: bytes) -> tuple[ClusterMember, ...]:
    value = _parse(messages_pb2.Ping(), data, "Ping")
    return tuple(member_from_proto(member) for member in value.gossip)


def encode_ack(
    *,
    success: bool,
    target_node_id: str,
    gossip: tuple[ClusterMember, ...],
) -> bytes:
    value = messages_pb2.Ack(success=success, target_node_id=target_node_id)
    value.gossip.extend(member_to_proto(member) for member in gossip)
    return value.SerializeToString()


def decode_ack(data: bytes) -> AckData:
    value = _parse(messages_pb2.Ack(), data, "Ack")
    return AckData(
        value.success,
        value.target_node_id,
        tuple(member_from_proto(member) for member in value.gossip),
    )


def encode_ping_request(
    *,
    target: ClusterMember,
    gossip: tuple[ClusterMember, ...],
) -> bytes:
    value = messages_pb2.PingRequest(target=member_to_proto(target))
    value.gossip.extend(member_to_proto(member) for member in gossip)
    return value.SerializeToString()


def decode_ping_request(data: bytes) -> tuple[ClusterMember, tuple[ClusterMember, ...]]:
    value = _parse(messages_pb2.PingRequest(), data, "PingRequest")
    return (
        member_from_proto(value.target),
        tuple(member_from_proto(member) for member in value.gossip),
    )


def encode_gossip(members: tuple[ClusterMember, ...]) -> bytes:
    value = messages_pb2.Gossip()
    value.members.extend(member_to_proto(member) for member in members)
    return value.SerializeToString()


def decode_gossip(data: bytes) -> tuple[ClusterMember, ...]:
    value = _parse(messages_pb2.Gossip(), data, "Gossip")
    return tuple(member_from_proto(member) for member in value.members)


def encode_forwarded_request(
    *,
    task_name: str,
    payload: object,
    routing_key: str,
    origin_node_id: str,
    remaining_timeout_ms: int,
) -> bytes:
    if not origin_node_id:
        raise DecodeError("origin_node_id is required")
    if remaining_timeout_ms < 0:
        raise DecodeError("remaining_timeout_ms cannot be negative")

    task = messages_pb2.TaskRequest()
    task.ParseFromString(encode_task_request(task_name, payload, routing_key=routing_key))
    return messages_pb2.ForwardedTaskRequest(
        request=task,
        origin_node_id=origin_node_id,
        remaining_timeout_ms=remaining_timeout_ms,
    ).SerializeToString()


def decode_forwarded_request(data: bytes) -> ForwardedTaskData:
    value = _parse(
        messages_pb2.ForwardedTaskRequest(),
        data,
        "ForwardedTaskRequest",
    )
    if not value.origin_node_id:
        raise DecodeError("origin_node_id is required")
    return ForwardedTaskData(
        task=decode_task_request(value.request.SerializeToString()),
        origin_node_id=value.origin_node_id,
        remaining_timeout_ms=value.remaining_timeout_ms,
    )
