"""In-memory message model used by the framed TCP protocol."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import IntEnum


class MessageType(IntEnum):
    REQUEST = 1
    RESPONSE = 2
    ERROR = 3
    HEARTBEAT = 4
    JOIN_REQUEST = 5
    JOIN_RESPONSE = 6
    PING = 7
    ACK = 8
    PING_REQ = 9
    GOSSIP = 10
    FORWARDED_REQUEST = 11
    CRDT_MUTATE_REQUEST = 12
    CRDT_READ_REQUEST = 13
    CRDT_REPLICATE = 14
    CRDT_FETCH = 15
    CRDT_DIGEST = 16
    CRDT_DIGEST_RESPONSE = 17
    CRDT_RESPONSE = 18


@dataclass(slots=True, frozen=True)
class Message:
    msg_type: MessageType
    sender_id: str
    correlation_id: str
    timestamp_ms: int
    ttl: int
    payload: bytes
    traceparent: str = ""
    tracestate: str = ""

    @classmethod
    def new_request(
        cls,
        *,
        sender_id: str,
        payload: bytes,
        correlation_id: str | None = None,
        ttl: int = 8,
        msg_type: MessageType = MessageType.REQUEST,
        traceparent: str = "",
        tracestate: str = "",
    ) -> Message:
        return cls(
            msg_type=msg_type,
            sender_id=sender_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            timestamp_ms=int(time.time() * 1000),
            ttl=ttl,
            payload=payload,
            traceparent=traceparent,
            tracestate=tracestate,
        )

    @classmethod
    def new_response(
        cls,
        *,
        sender_id: str,
        correlation_id: str,
        payload: bytes,
        msg_type: MessageType = MessageType.RESPONSE,
        ttl: int = 8,
        traceparent: str = "",
        tracestate: str = "",
    ) -> Message:
        return cls(
            msg_type=msg_type,
            sender_id=sender_id,
            correlation_id=correlation_id,
            timestamp_ms=int(time.time() * 1000),
            ttl=ttl,
            payload=payload,
            traceparent=traceparent,
            tracestate=tracestate,
        )
