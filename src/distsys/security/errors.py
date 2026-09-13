"""TLS and peer-identity failures."""


class TlsConfigurationError(ValueError):
    """Raised when TLS settings cannot produce a secure context."""


class TlsPeerIdentityError(ConnectionError):
    """Raised when an authenticated certificate does not match the expected node id."""
