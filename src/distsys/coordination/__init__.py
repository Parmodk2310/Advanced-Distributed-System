"""etcd-backed cluster coordination for Phase 5."""

from distsys.coordination.errors import CoordinationError, CoordinationUnavailableError
from distsys.coordination.models import CoordinationHealth, CoordinationMember, LeaseHandle

__all__ = [
    "CoordinationError",
    "CoordinationHealth",
    "CoordinationMember",
    "CoordinationUnavailableError",
    "LeaseHandle",
]
