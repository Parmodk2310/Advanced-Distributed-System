"""Async wrapper around the blocking etcd3gw gRPC-gateway client."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from distsys.coordination.errors import CoordinationUnavailableError
from distsys.coordination.models import (
    CoordinationMember,
    LeaseHandle,
    member_key,
    node_metadata_key,
)


class EtcdGatewayCoordinationClient:
    def __init__(
        self,
        endpoints: tuple[str, ...],
        *,
        namespace: str = "/distsys/v1",
        timeout_seconds: float = 3.0,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not endpoints:
            raise ValueError("at least one etcd endpoint is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.endpoints = endpoints
        self.namespace = "/" + namespace.strip("/")
        self.timeout_seconds = timeout_seconds
        self._client_factory = client_factory
        self._client: Any | None = None
        self._leases: dict[int, Any] = {}
        self.active_endpoint: str | None = None

    def _factory(self, endpoint: str) -> Any:
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or not parsed.port:
            raise ValueError(f"invalid etcd endpoint: {endpoint}")
        factory = self._client_factory
        if factory is None:
            try:
                from etcd3gw.client import Etcd3Client
            except ImportError as exc:
                raise CoordinationUnavailableError(
                    "etcd3gw is required when ETCD_ENABLED=true"
                ) from exc
            factory = Etcd3Client
        return factory(
            host=parsed.hostname,
            port=parsed.port,
            protocol=parsed.scheme,
            timeout=self.timeout_seconds,
        )

    async def connect(self) -> None:
        errors: list[Exception] = []
        for endpoint in self.endpoints:
            client = self._factory(endpoint)
            try:
                await asyncio.to_thread(client.status)
            except Exception as exc:  # noqa: BLE001 - third-party etcd boundary
                errors.append(exc)
                continue
            self._client = client
            self.active_endpoint = endpoint
            return
        cause = errors[-1] if errors else None
        raise CoordinationUnavailableError("no etcd endpoint is reachable") from cause

    async def close(self) -> None:
        self._client = None
        self._leases.clear()
        self.active_endpoint = None

    def _require_client(self) -> Any:
        if self._client is None:
            raise CoordinationUnavailableError("etcd client is not connected")
        return self._client

    async def grant_lease(self, ttl_seconds: int) -> LeaseHandle:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        client = self._require_client()
        try:
            lease = await asyncio.to_thread(client.lease, ttl_seconds)
        except Exception as exc:
            raise CoordinationUnavailableError("failed to grant etcd lease") from exc
        handle = LeaseHandle(int(lease.id), ttl_seconds)
        self._leases[handle.lease_id] = lease
        return handle

    async def refresh_lease(self, lease: LeaseHandle) -> None:
        raw = self._leases.get(lease.lease_id)
        if raw is None:
            raise CoordinationUnavailableError("unknown etcd lease")
        try:
            ttl = await asyncio.to_thread(raw.refresh)
        except Exception as exc:
            raise CoordinationUnavailableError("failed to refresh etcd lease") from exc
        if isinstance(ttl, (int, float)) and ttl <= 0:
            raise CoordinationUnavailableError("etcd lease expired")

    async def register_member(self, member: CoordinationMember, lease: LeaseHandle) -> None:
        client = self._require_client()
        raw = self._leases.get(lease.lease_id)
        if raw is None:
            raise CoordinationUnavailableError("unknown etcd lease")
        try:
            await asyncio.to_thread(
                client.put,
                member_key(self.namespace, member.node_id),
                member.to_json(),
                raw,
            )
        except Exception as exc:
            raise CoordinationUnavailableError("failed to register etcd member") from exc

    async def put_node_metadata(self, member: CoordinationMember) -> None:
        client = self._require_client()
        try:
            await asyncio.to_thread(
                client.put,
                node_metadata_key(self.namespace, member.node_id),
                member.to_json(),
            )
        except Exception as exc:
            raise CoordinationUnavailableError("failed to persist etcd node metadata") from exc

    async def discover_members(self) -> tuple[CoordinationMember, ...]:
        client = self._require_client()
        prefix = f"{self.namespace}/members/"
        try:
            rows = await asyncio.to_thread(client.get_prefix, prefix)
        except Exception as exc:
            raise CoordinationUnavailableError("failed to discover etcd members") from exc
        members: list[CoordinationMember] = []
        for value, _metadata in rows:
            members.append(CoordinationMember.from_json(value))
        return tuple(sorted(members, key=lambda item: item.node_id))
