"""Coordination-layer failures."""


class CoordinationError(RuntimeError):
    """Base coordination failure."""


class CoordinationUnavailableError(CoordinationError):
    """Raised when etcd coordination cannot be reached."""
