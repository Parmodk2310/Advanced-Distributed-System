"""Safe TCP frame encoding and incremental decoding."""

from __future__ import annotations

import asyncio
import struct

from distsys.protocol.codec import decode_envelope, encode_envelope
from distsys.protocol.errors import (
    FrameTooLarge,
    InvalidFrameLength,
    InvalidMagic,
    InvalidMessageType,
    UnsupportedVersion,
)
from distsys.protocol.message import Message, MessageType

MAGIC = b"DS"
PROTOCOL_VERSION = 1
HEADER_STRUCT = struct.Struct("!2sBBI")
HEADER_SIZE = HEADER_STRUCT.size
DEFAULT_MAX_FRAME_SIZE = 4 * 1024 * 1024


def _validate_header(
    magic: bytes,
    version: int,
    raw_type: int,
    body_length: int,
    *,
    max_frame_size: int,
) -> MessageType:
    if magic != MAGIC:
        raise InvalidMagic(f"expected {MAGIC!r}, got {magic!r}")
    if version != PROTOCOL_VERSION:
        raise UnsupportedVersion(f"unsupported protocol version: {version}")
    try:
        msg_type = MessageType(raw_type)
    except ValueError as exc:
        raise InvalidMessageType(f"unknown message type: {raw_type}") from exc
    if body_length <= 0:
        raise InvalidFrameLength(f"body length must be > 0, got {body_length}")
    if body_length > max_frame_size:
        raise FrameTooLarge(f"frame body {body_length} exceeds limit {max_frame_size}")
    return msg_type


def encode_frame(message: Message, *, max_frame_size: int = DEFAULT_MAX_FRAME_SIZE) -> bytes:
    body = encode_envelope(message)
    if not body:
        raise InvalidFrameLength("encoded envelope is empty")
    if len(body) > max_frame_size:
        raise FrameTooLarge(f"frame body {len(body)} exceeds limit {max_frame_size}")
    header = HEADER_STRUCT.pack(MAGIC, PROTOCOL_VERSION, int(message.msg_type), len(body))
    return header + body


async def read_message(
    reader: asyncio.StreamReader,
    *,
    max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
) -> Message:
    header = await reader.readexactly(HEADER_SIZE)
    magic, version, raw_type, body_length = HEADER_STRUCT.unpack(header)
    msg_type = _validate_header(
        magic,
        version,
        raw_type,
        body_length,
        max_frame_size=max_frame_size,
    )
    body = await reader.readexactly(body_length)
    return decode_envelope(msg_type, body)


class FrameDecoder:
    """Incremental decoder used to prove correctness under arbitrary TCP chunking."""

    def __init__(self, *, max_frame_size: int = DEFAULT_MAX_FRAME_SIZE):
        self.max_frame_size = max_frame_size
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[Message]:
        self._buffer.extend(data)
        messages: list[Message] = []

        while True:
            if len(self._buffer) < HEADER_SIZE:
                break

            magic, version, raw_type, body_length = HEADER_STRUCT.unpack(
                self._buffer[:HEADER_SIZE]
            )
            msg_type = _validate_header(
                magic,
                version,
                raw_type,
                body_length,
                max_frame_size=self.max_frame_size,
            )

            frame_size = HEADER_SIZE + body_length
            if len(self._buffer) < frame_size:
                break

            body = bytes(self._buffer[HEADER_SIZE:frame_size])
            del self._buffer[:frame_size]
            messages.append(decode_envelope(msg_type, body))

        return messages
