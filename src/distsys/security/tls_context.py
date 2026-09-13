"""TLS 1.3 context construction."""

from __future__ import annotations

import ssl

from distsys.security.errors import TlsConfigurationError
from distsys.utils.config import Settings


def _validate_files(settings: Settings) -> None:
    if not settings.tls_enabled:
        return
    missing = [
        name
        for name, value in (
            ("TLS_CA_FILE", settings.tls_ca_file),
            ("TLS_CERT_FILE", settings.tls_cert_file),
            ("TLS_KEY_FILE", settings.tls_key_file),
        )
        if not value
    ]
    if missing:
        raise TlsConfigurationError(f"missing TLS settings: {', '.join(missing)}")


def build_server_context(settings: Settings) -> ssl.SSLContext | None:
    if not settings.tls_enabled:
        return None
    _validate_files(settings)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(settings.tls_cert_file, settings.tls_key_file)
    context.load_verify_locations(cafile=settings.tls_ca_file)
    context.verify_mode = ssl.CERT_REQUIRED if settings.mtls_required else ssl.CERT_OPTIONAL
    return context


def build_client_context(settings: Settings) -> ssl.SSLContext | None:
    if not settings.tls_enabled:
        return None
    _validate_files(settings)
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=settings.tls_ca_file)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(settings.tls_cert_file, settings.tls_key_file)
    context.check_hostname = True
    return context
