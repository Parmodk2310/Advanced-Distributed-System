"""One-shot Phase-4 peer transport plus protocol-specific adapters."""

from __future__ import annotations

import asyncio
import ssl
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from typing import Any, Protocol

from distsys.chaos.routing import peer_routing_enabled, resolve_peer_endpoint
from distsys.cluster.member import ClusterMember
from distsys.protocol.framing import DEFAULT_MAX_FRAME_SIZE, encode_frame, read_message
from distsys.protocol.message import Message, MessageType
from distsys.replication.causal_repair import PeerCrdtFetch
from distsys.replication.codec import (
    CrdtMutationData,
    CrdtReadData,
    CrdtResponseData,
    decode_crdt_response,
    decode_digest_response,
    encode_digest_request,
    encode_fetch_request,
    encode_mutation_request,
    encode_read_request,
    encode_replication,
)
from distsys.replication.digest import CrdtDigestEntry
from distsys.resilience.deadline import Deadline, DeadlineExceeded
from distsys.security.errors import TlsPeerIdentityError
from distsys.security.identity import verify_node_identity
from distsys.storage import StoredCrdtEntry
from distsys.storage.protocol import CrdtStateStore


class CrdtPeerProtocolError(ConnectionError):
    """Peer returned an invalid CRDT protocol response."""


class CrdtRemoteError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ReplicationClient(Protocol):
    async def replicate(
        self,
        peer: ClusterMember,
        state: StoredCrdtEntry,
        *,
        timeout_seconds: float,
    ) -> None: ...


class FetchClient(Protocol):
    async def fetch(
        self,
        peer: ClusterMember,
        key: str,
        *,
        timeout_seconds: float,
    ) -> CrdtResponseData: ...


class AntiEntropyClient(ReplicationClient, FetchClient, Protocol):
    async def digest(
        self,
        peer: ClusterMember,
        entries: tuple[CrdtDigestEntry, ...],
        *,
        batch_size: int,
        timeout_seconds: float,
    ) -> tuple[CrdtDigestEntry, ...]: ...


class CrdtPeerClient:
    def __init__(
        self,
        *,
        local_node_id: str,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.local_node_id = local_node_id
        self.max_frame_size = max_frame_size
        self.ssl_context = ssl_context
        self.metrics: Any | None = None
        self.tracing: Any | None = None

    async def _exchange(
        self,
        peer: ClusterMember,
        message: Message,
        *,
        timeout_seconds: float,
    ) -> Message:
        tracing = getattr(self, "tracing", None)
        metrics = getattr(self, "metrics", None)
        if (
            metrics is None
            and (tracing is None or not tracing.enabled)
            and not peer_routing_enabled()
        ):
            return await self._exchange_raw(peer, message, timeout_seconds=timeout_seconds)

        operation = {
            MessageType.CRDT_REPLICATE: "replicate",
            MessageType.CRDT_FETCH: "fetch",
            MessageType.CRDT_DIGEST: "digest",
            MessageType.CRDT_READ_REQUEST: "read",
            MessageType.CRDT_MUTATE_REQUEST: "write",
        }.get(message.msg_type, "request")
        host, port = resolve_peer_endpoint(peer.node_id, peer.host, peer.port)
        peer = replace(peer, host=host, port=port)
        span_context = (
            tracing.tracer.start_as_current_span(
                "distsys.peer_rpc",
                attributes={
                    "distsys.node.id": self.local_node_id,
                    "distsys.peer.id": peer.node_id,
                    "distsys.operation": operation,
                },
            )
            if tracing is not None and tracing.enabled
            else nullcontext()
        )
        started = time.perf_counter()
        status = "error"
        with span_context:
            if tracing is not None and tracing.enabled:
                carrier: dict[str, str] = {}
                tracing.inject(carrier)
                message = replace(
                    message,
                    traceparent=carrier.get("traceparent", ""),
                    tracestate=carrier.get("tracestate", ""),
                )
            try:
                response = await self._exchange_raw(peer, message, timeout_seconds=timeout_seconds)
                status = "success"
                return response
            except TimeoutError:
                status = "timeout"
                raise
            finally:
                if metrics is not None:
                    metrics.peer_rpc(operation, status, time.perf_counter() - started)

    async def _exchange_raw(
        self,
        peer: ClusterMember,
        message: Message,
        *,
        timeout_seconds: float,
    ) -> Message:
        if timeout_seconds <= 0:
            raise TimeoutError("CRDT peer exchange timeout exhausted")
        async with asyncio.timeout(timeout_seconds):
            if self.ssl_context is None:
                reader, writer = await asyncio.open_connection(peer.host, peer.port)
            else:
                reader, writer = await asyncio.open_connection(
                    peer.host,
                    peer.port,
                    ssl=self.ssl_context,
                    server_hostname=peer.node_id,
                )
                ssl_object = writer.get_extra_info("ssl_object")
                if ssl_object is None:
                    raise TlsPeerIdentityError("TLS peer did not expose an SSL object")
                verify_node_identity(ssl_object.getpeercert(), peer.node_id)
            try:
                writer.write(encode_frame(message, max_frame_size=self.max_frame_size))
                await writer.drain()
                try:
                    response = await read_message(reader, max_frame_size=self.max_frame_size)
                except asyncio.IncompleteReadError as exc:
                    raise CrdtPeerProtocolError(
                        "peer closed connection before sending a complete response"
                    ) from exc
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass
        if response.correlation_id != message.correlation_id:
            raise CrdtPeerProtocolError("CRDT peer correlation mismatch")
        return response

    async def _crdt_round_trip(
        self,
        peer: ClusterMember,
        *,
        msg_type: MessageType,
        payload: bytes,
        timeout_seconds: float,
        raise_remote: bool = True,
    ) -> CrdtResponseData:
        request = Message.new_request(
            sender_id=self.local_node_id,
            msg_type=msg_type,
            payload=payload,
        )
        response = await self._exchange(peer, request, timeout_seconds=timeout_seconds)
        if response.msg_type is not MessageType.CRDT_RESPONSE:
            raise CrdtPeerProtocolError(f"expected CRDT_RESPONSE, got {response.msg_type.name}")
        decoded = decode_crdt_response(response.payload)
        if raise_remote and not decoded.success:
            raise CrdtRemoteError(decoded.error_code, decoded.error_message)
        return decoded

    async def replicate(
        self,
        peer: ClusterMember,
        state: StoredCrdtEntry,
        *,
        timeout_seconds: float,
    ) -> None:
        await self._crdt_round_trip(
            peer,
            msg_type=MessageType.CRDT_REPLICATE,
            payload=encode_replication(state),
            timeout_seconds=timeout_seconds,
        )

    async def fetch(
        self,
        peer: ClusterMember,
        key: str,
        *,
        timeout_seconds: float,
    ) -> CrdtResponseData:
        return await self._crdt_round_trip(
            peer,
            msg_type=MessageType.CRDT_FETCH,
            payload=encode_fetch_request(key),
            timeout_seconds=timeout_seconds,
            raise_remote=False,
        )

    async def digest(
        self,
        peer: ClusterMember,
        entries: tuple[CrdtDigestEntry, ...],
        *,
        batch_size: int,
        timeout_seconds: float,
    ) -> tuple[CrdtDigestEntry, ...]:
        request = Message.new_request(
            sender_id=self.local_node_id,
            msg_type=MessageType.CRDT_DIGEST,
            payload=encode_digest_request(
                self.local_node_id,
                entries,
                batch_size=batch_size,
            ),
        )
        response = await self._exchange(peer, request, timeout_seconds=timeout_seconds)
        if response.msg_type is not MessageType.CRDT_DIGEST_RESPONSE:
            raise CrdtPeerProtocolError(
                f"expected CRDT_DIGEST_RESPONSE, got {response.msg_type.name}"
            )
        return decode_digest_response(response.payload)

    async def forward_mutation(
        self,
        peer: ClusterMember,
        request: CrdtMutationData,
        *,
        deadline: Deadline,
    ) -> CrdtResponseData:
        remaining = deadline.remaining()
        if remaining <= 0:
            raise DeadlineExceeded("CRDT request deadline exceeded before forwarding")
        forwarded = replace(
            request,
            forwarded=True,
            origin_node_id=request.origin_node_id or self.local_node_id,
            remaining_timeout_ms=max(1, int(remaining * 1000)),
        )
        return await self._crdt_round_trip(
            peer,
            msg_type=MessageType.CRDT_MUTATE_REQUEST,
            payload=encode_mutation_request(forwarded),
            timeout_seconds=deadline.remaining(),
        )

    async def forward_read(
        self,
        peer: ClusterMember,
        request: CrdtReadData,
        *,
        deadline: Deadline,
    ) -> CrdtResponseData:
        remaining = deadline.remaining()
        if remaining <= 0:
            raise DeadlineExceeded("CRDT request deadline exceeded before forwarding")
        forwarded = replace(
            request,
            forwarded=True,
            origin_node_id=request.origin_node_id or self.local_node_id,
            remaining_timeout_ms=max(1, int(remaining * 1000)),
        )
        return await self._crdt_round_trip(
            peer,
            msg_type=MessageType.CRDT_READ_REQUEST,
            payload=encode_read_request(forwarded),
            timeout_seconds=deadline.remaining(),
        )


class ReplicationTransportAdapter:
    """Adapts node-id outbox work to addressable cluster members."""

    def __init__(
        self,
        client: ReplicationClient,
        resolver: Callable[[str], ClusterMember | None],
        timeout_seconds: float,
    ) -> None:
        self.client = client
        self.resolver = resolver
        self.timeout_seconds = timeout_seconds

    async def send_state(self, peer_node_id: str, state: StoredCrdtEntry) -> None:
        peer = self.resolver(peer_node_id)
        if peer is None:
            raise ConnectionError(f"peer {peer_node_id} is not currently ALIVE")
        await self.client.replicate(peer, state, timeout_seconds=self.timeout_seconds)


class CausalRepairPeerAdapter:
    def __init__(self, client: FetchClient, *, timeout_cap_seconds: float = 1.0) -> None:
        self.client = client
        self.timeout_cap_seconds = timeout_cap_seconds

    async def fetch_state(
        self,
        peer: ClusterMember,
        key: str,
        deadline: Deadline,
    ) -> PeerCrdtFetch:
        timeout = min(self.timeout_cap_seconds, deadline.remaining())
        if timeout <= 0:
            raise DeadlineExceeded("causal repair deadline exhausted")
        response = await self.client.fetch(peer, key, timeout_seconds=timeout)
        return PeerCrdtFetch(
            peer_node_id=peer.node_id,
            entry=response.state if response.success else None,
            causal_frontier=response.peer_frontier,
        )


class AntiEntropyPeerAdapter:
    def __init__(
        self,
        client: AntiEntropyClient,
        store: CrdtStateStore,
        *,
        timeout_seconds: float = 1.0,
    ) -> None:
        self.client = client
        self.store = store
        self.timeout_seconds = timeout_seconds

    async def exchange_digest(
        self,
        peer: ClusterMember,
        digest_entries: tuple[CrdtDigestEntry, ...],
    ) -> tuple[CrdtDigestEntry, ...]:
        return await self.client.digest(
            peer,
            digest_entries,
            batch_size=max(1, len(digest_entries)),
            timeout_seconds=self.timeout_seconds,
        )

    async def fetch_state(self, peer: ClusterMember, key: str) -> StoredCrdtEntry | None:
        response = await self.client.fetch(peer, key, timeout_seconds=self.timeout_seconds)
        return response.state if response.success else None

    async def send_state(self, peer: ClusterMember, state: StoredCrdtEntry) -> None:
        await self.client.replicate(peer, state, timeout_seconds=self.timeout_seconds)

    async def send_metadata(
        self,
        peer: ClusterMember,
        key: str,
        causal_context,
    ) -> None:
        local = await self.store.get(key)
        if local is None:
            return
        digest = CrdtDigestEntry(
            key=local.key,
            crdt_type=local.crdt_type,
            state_version=local.state_version,
            causal_context=causal_context,
        )
        await self.client.digest(
            peer,
            (digest,),
            batch_size=1,
            timeout_seconds=self.timeout_seconds,
        )
