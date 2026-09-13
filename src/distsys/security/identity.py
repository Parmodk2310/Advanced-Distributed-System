"""Logical cluster node identity verification for mTLS."""

from __future__ import annotations

from collections.abc import Mapping

from distsys.security.certificate import dns_sans
from distsys.security.errors import TlsPeerIdentityError


def verify_node_identity(cert: Mapping[str, object], expected_node_id: str) -> None:
    if not expected_node_id:
        raise ValueError("expected_node_id must not be empty")
    if expected_node_id not in dns_sans(cert):
        raise TlsPeerIdentityError(
            f"authenticated peer certificate does not identify {expected_node_id}"
        )
