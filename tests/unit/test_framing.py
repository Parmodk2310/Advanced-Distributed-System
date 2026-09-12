import pytest

from distsys.protocol.errors import FrameTooLarge, InvalidMagic, UnsupportedVersion
from distsys.protocol.framing import (
    DEFAULT_MAX_FRAME_SIZE,
    HEADER_STRUCT,
    FrameDecoder,
    encode_frame,
)
from distsys.protocol.message import Message


def message(correlation_id: str = "corr-1") -> Message:
    return Message.new_request(
        sender_id="client",
        correlation_id=correlation_id,
        payload=b"hello",
    )


def test_frame_round_trip():
    original = message()
    decoded = FrameDecoder().feed(encode_frame(original))
    assert decoded == [original]


def test_partial_frame_is_reassembled():
    original = message()
    frame = encode_frame(original)
    decoder = FrameDecoder()
    output = []
    for byte in frame:
        output.extend(decoder.feed(bytes([byte])))
    assert output == [original]


def test_two_frames_in_one_read():
    first = message("a")
    second = message("b")
    decoded = FrameDecoder().feed(encode_frame(first) + encode_frame(second))
    assert decoded == [first, second]


def test_bad_magic_rejected():
    frame = bytearray(encode_frame(message()))
    frame[0:2] = b"XX"
    with pytest.raises(InvalidMagic):
        FrameDecoder().feed(bytes(frame))


def test_unsupported_version_rejected():
    frame = bytearray(encode_frame(message()))
    frame[2] = 99
    with pytest.raises(UnsupportedVersion):
        FrameDecoder().feed(bytes(frame))


def test_oversized_payload_rejected_before_body_arrives():
    header = HEADER_STRUCT.pack(b"DS", 1, 1, DEFAULT_MAX_FRAME_SIZE + 1)
    with pytest.raises(FrameTooLarge):
        FrameDecoder().feed(header)
