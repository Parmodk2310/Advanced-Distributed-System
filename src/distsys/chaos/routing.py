"""Chaos-only peer endpoint rewriting for Toxiproxy interception.

The mapping is ignored unless RUN_CHAOS_TESTS=1, so Phase 1–5 runtime routing is
bit-for-bit equivalent in normal profiles.
"""

from __future__ import annotations

import os


def _mapping() -> dict[str, tuple[str, int]]:
    raw = os.getenv("PHASE6_PEER_PROXY_MAP", "").strip()
    if not raw:
        return {}
    result: dict[str, tuple[str, int]] = {}
    for item in raw.split(","):
        try:
            node_id, endpoint = item.split("=", 1)
            host, port_text = endpoint.rsplit(":", 1)
            port = int(port_text)
        except (ValueError, TypeError) as exc:
            raise ValueError("PHASE6_PEER_PROXY_MAP must use node=host:port entries") from exc
        if not node_id or not host or not 1 <= port <= 65535:
            raise ValueError("PHASE6_PEER_PROXY_MAP contains an invalid endpoint")
        result[node_id] = (host, port)
    return result


def peer_routing_enabled() -> bool:
    """Return true only for the explicit Phase 6 chaos proxy profile."""
    return os.getenv("RUN_CHAOS_TESTS") == "1" and bool(
        os.getenv("PHASE6_PEER_PROXY_MAP", "").strip()
    )


def resolve_peer_endpoint(node_id: str | None, host: str, port: int) -> tuple[str, int]:
    if os.getenv("RUN_CHAOS_TESTS") != "1" or not node_id:
        return host, port
    return _mapping().get(node_id, (host, port))
