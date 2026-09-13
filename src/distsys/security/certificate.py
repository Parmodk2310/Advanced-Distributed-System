"""Helpers for inspecting TLS peer certificates returned by Python ssl."""

from __future__ import annotations

from collections.abc import Mapping


def _sans(cert: Mapping[str, object], kind: str) -> frozenset[str]:
    raw = cert.get("subjectAltName", ())
    values: set[str] = set()
    if isinstance(raw, (tuple, list)):
        for item in raw:
            if (
                isinstance(item, (tuple, list))
                and len(item) == 2
                and item[0] == kind
                and isinstance(item[1], str)
            ):
                values.add(item[1])
    return frozenset(values)


def dns_sans(cert: Mapping[str, object]) -> frozenset[str]:
    return _sans(cert, "DNS")


def ip_sans(cert: Mapping[str, object]) -> frozenset[str]:
    return _sans(cert, "IP Address")
