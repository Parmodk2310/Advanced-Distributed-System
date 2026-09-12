"""Protocol and transport exceptions."""


class ProtocolError(Exception):
    """Base class for protocol failures."""


class InvalidMagic(ProtocolError):
    pass


class UnsupportedVersion(ProtocolError):
    pass


class InvalidMessageType(ProtocolError):
    pass


class InvalidFrameLength(ProtocolError):
    pass


class FrameTooLarge(ProtocolError):
    pass


class DecodeError(ProtocolError):
    pass
