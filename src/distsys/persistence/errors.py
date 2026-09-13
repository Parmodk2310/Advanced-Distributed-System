"""Persistence-specific failures for Phase 5."""


class PersistenceError(RuntimeError):
    """Base class for durable-state failures."""


class PersistenceUnavailableError(PersistenceError):
    """Raised when durable state cannot be accessed or committed."""


class PersistenceBackpressureError(PersistenceError):
    """Raised when bounded persistence admission cannot be obtained."""


class RepositoryIntegrityError(PersistenceError):
    """Raised when SQLite integrity validation fails."""


class RepositorySchemaError(PersistenceError):
    """Raised for unsupported or failed schema migrations."""


class NodeIdentityMismatchError(PersistenceError):
    """Raised when a durable database belongs to another configured node id."""
