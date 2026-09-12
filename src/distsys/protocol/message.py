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


@dataclass(slots=True, frozen=True)
class Message:
    msg_type: MessageType
    sender_id: str
    correlation_id: str
    timestamp_ms: int
    ttl: int
    payload: bytes

    @classmethod
    def new_request(
        cls,
        *,
        sender_id: str,
        payload: bytes,
        correlation_id: str | None = None,
        ttl: int = 8,
    ) -> "Message":
        return cls(
            msg_type=MessageType.REQUEST,
            sender_id=sender_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            timestamp_ms=int(time.time() * 1000),
            ttl=ttl,
            payload=payload,
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
    ) -> "Message":
        return cls(
            msg_type=msg_type,
            sender_id=sender_id,
            correlation_id=correlation_id,
            timestamp_ms=int(time.time() * 1000),
            ttl=ttl,
            payload=payload,
        )
