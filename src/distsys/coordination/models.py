"""Coordination metadata exchanged through etcd."""

from __future__ import annotations

import json
from dataclasses import dataclass


def _namespace(value: str) -> str:
    cleaned = "/" + value.strip("/")
    if cleaned == "/":
        raise ValueError("coordination namespace must not be empty")
    return cleaned


def member_key(namespace: str, node_id: str) -> str:
    if not node_id:
        raise ValueError("node_id must not be empty")
    return f"{_namespace(namespace)}/members/{node_id}"


def node_metadata_key(namespace: str, node_id: str) -> str:
    if not node_id:
        raise ValueError("node_id must not be empty")
    return f"{_namespace(namespace)}/nodes/{node_id}/metadata"


@dataclass(frozen=True, slots=True)
class LeaseHandle:
    lease_id: int
    ttl_seconds: int

    def __post_init__(self) -> None:
        if self.lease_id <= 0:
            raise ValueError("lease_id must be positive")
        if self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")


@dataclass(frozen=True, slots=True)
class CoordinationMember:
    node_id: str
    node_uuid: str
    host: str
    port: int
    membership_incarnation: int
    protocol_version: int
    release: str
    tls_required: bool

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id must not be empty")
        if not self.node_uuid:
            raise ValueError("node_uuid must not be empty")
        if not self.host:
            raise ValueError("host must not be empty")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.membership_incarnation < 1:
            raise ValueError("membership_incarnation must be positive")
        if self.protocol_version < 1:
            raise ValueError("protocol_version must be positive")
        if not self.release:
            raise ValueError("release must not be empty")

    def to_json(self) -> str:
        return json.dumps(
            {
                "host": self.host,
                "membership_incarnation": self.membership_incarnation,
                "node_id": self.node_id,
                "node_uuid": self.node_uuid,
                "port": self.port,
                "protocol_version": self.protocol_version,
                "release": self.release,
                "tls_required": self.tls_required,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> CoordinationMember:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid coordination member JSON") from exc
        if not isinstance(data, dict):
            raise TypeError("coordination member payload must be an object")
        return cls(
            node_id=str(data["node_id"]),
            node_uuid=str(data["node_uuid"]),
            host=str(data["host"]),
            port=int(data["port"]),
            membership_incarnation=int(data["membership_incarnation"]),
            protocol_version=int(data["protocol_version"]),
            release=str(data["release"]),
            tls_required=bool(data["tls_required"]),
        )


@dataclass(frozen=True, slots=True)
class CoordinationHealth:
    healthy: bool
    connected: bool
    lease_id: int | None = None
    message: str = ""
