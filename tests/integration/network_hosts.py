"""Network addresses for integration tests across Linux and WSL2."""

from __future__ import annotations

import platform
import socket

_LOOPBACK = "127.0.0.1"
_ROUTE_PROBE = ("192.0.2.1", 9)  # TEST-NET-1; UDP connect performs route lookup only.


def is_wsl() -> bool:
    """Return whether the test process is running inside WSL."""

    release = platform.release().casefold()
    version = platform.version().casefold()
    return "microsoft" in release or "microsoft" in version


def routed_ipv4_address() -> str:
    """Return the kernel-selected IPv4 address for the default route.

    UDP ``connect`` does not transmit data here; it only asks the kernel which
    local address would be used for the route. If a runner has no default IPv4
    route, loopback remains a safe fallback.
    """

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(_ROUTE_PROBE)
        host = str(sock.getsockname()[0])
    except OSError:
        return _LOOPBACK
    finally:
        sock.close()
    return host if host and not host.startswith("127.") else _LOOPBACK


def local_tcp_test_host() -> str:
    """Return a TCP test host that avoids WSL localhost forwarding for port 0."""

    return routed_ipv4_address() if is_wsl() else _LOOPBACK
