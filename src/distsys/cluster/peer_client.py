"""One-shot peer RPC plus task retry/circuit-breaker boundaries."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from distsys.cluster.codec import (
    AckData,
    decode_ack,
    decode_join_response,
    encode_forwarded_request,
    encode_gossip,
    encode_join_request,
    encode_ping,
    encode_ping_request,
)
from distsys.cluster.member import ClusterMember, SeedAddress
from distsys.proto import messages_pb2
from distsys.protocol.codec import decode_task_response
from distsys.protocol.framing import DEFAULT_MAX_FRAME_SIZE, encode_frame, read_message
from distsys.protocol.message import Message, MessageType
from distsys.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError
from distsys.resilience.deadline import Deadline, DeadlineExceeded
from distsys.resilience.retry import RetryPolicy, retry_async

logger = logging.getLogger("distsys.cluster.peer_client")


class PeerProtocolError(ConnectionError):
    """Raised when a peer violates the framed request/response protocol."""


class PeerTransportError(ConnectionError):
    """Raised after retryable peer transport failures are exhausted."""


class PeerApplicationError(RuntimeError):
    """Structured application error returned by a reachable peer."""

    def __init__(self, code: messages_pb2.ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_RETRYABLE = (ConnectionError, TimeoutError, OSError, PeerProtocolError)


class PeerClient:
    def __init__(
        self,
        *,
        local_node_id: str,
        retry_policy: RetryPolicy,
        circuit_breaker_failure_threshold: int,
        circuit_breaker_recovery_seconds: float,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
    ) -> None:
        self.local_node_id = local_node_id
        self.retry_policy = retry_policy
        self.circuit_breaker_failure_threshold = circuit_breaker_failure_threshold
        self.circuit_breaker_recovery_seconds = circuit_breaker_recovery_seconds
        self.max_frame_size = max_frame_size
        self._breakers: dict[str, CircuitBreaker] = {}

    def breaker_for(self, node_id: str) -> CircuitBreaker:
        breaker = self._breakers.get(node_id)
        if breaker is None:
            breaker = CircuitBreaker(
                failure_threshold=self.circuit_breaker_failure_threshold,
                recovery_timeout_seconds=self.circuit_breaker_recovery_seconds,
            )
            self._breakers[node_id] = breaker
        return breaker

    async def _exchange_endpoint(
        self,
        host: str,
        port: int,
        message: Message,
        *,
        timeout_seconds: float,
    ) -> Message:
        if timeout_seconds <= 0:
            raise TimeoutError("peer exchange timeout exhausted")
        async with asyncio.timeout(timeout_seconds):
            reader, writer = await asyncio.open_connection(host, port)
            try:
                writer.write(encode_frame(message, max_frame_size=self.max_frame_size))
                await writer.drain()
                response = await read_message(reader, max_frame_size=self.max_frame_size)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass
        if response.correlation_id != message.correlation_id:
            raise PeerProtocolError(
                f"expected correlation {message.correlation_id}, got {response.correlation_id}"
            )
        return response

    async def join(
        self,
        seed: SeedAddress,
        local_member: ClusterMember,
        *,
        timeout_seconds: float,
    ) -> tuple[ClusterMember, ...]:
        request = Message.new_request(
            sender_id=self.local_node_id,
            payload=encode_join_request(local_member),
            msg_type=MessageType.JOIN_REQUEST,
        )
        response = await self._exchange_endpoint(
            seed.host, seed.port, request, timeout_seconds=timeout_seconds
        )
        if response.msg_type is not MessageType.JOIN_RESPONSE:
            raise PeerProtocolError(f"expected JOIN_RESPONSE, got {response.msg_type.name}")
        return decode_join_response(response.payload)

    async def ping(
        self,
        peer: ClusterMember,
        gossip: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData:
        request = Message.new_request(
            sender_id=self.local_node_id,
            payload=encode_ping(gossip),
            msg_type=MessageType.PING,
        )
        response = await self._exchange_endpoint(
            peer.host, peer.port, request, timeout_seconds=timeout_seconds
        )
        if response.msg_type is not MessageType.ACK:
            raise PeerProtocolError(f"expected ACK, got {response.msg_type.name}")
        return decode_ack(response.payload)

    async def ping_request(
        self,
        helper: ClusterMember,
        target: ClusterMember,
        gossip: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData:
        request = Message.new_request(
            sender_id=self.local_node_id,
            payload=encode_ping_request(target=target, gossip=gossip),
            msg_type=MessageType.PING_REQ,
        )
        response = await self._exchange_endpoint(
            helper.host, helper.port, request, timeout_seconds=timeout_seconds
        )
        if response.msg_type is not MessageType.ACK:
            raise PeerProtocolError(f"expected ACK, got {response.msg_type.name}")
        return decode_ack(response.payload)

    async def gossip(
        self,
        peer: ClusterMember,
        members: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData:
        request = Message.new_request(
            sender_id=self.local_node_id,
            payload=encode_gossip(members),
            msg_type=MessageType.GOSSIP,
        )
        response = await self._exchange_endpoint(
            peer.host, peer.port, request, timeout_seconds=timeout_seconds
        )
        if response.msg_type is not MessageType.ACK:
            raise PeerProtocolError(f"expected ACK, got {response.msg_type.name}")
        return decode_ack(response.payload)

    async def forward_task(
        self,
        peer: ClusterMember,
        *,
        task_name: str,
        payload: Any,
        routing_key: str,
        origin_node_id: str,
        deadline: Deadline,
    ) -> Any:
        correlation_id = str(uuid.uuid4())
        breaker = self.breaker_for(peer.node_id)
        logger.info(
            "forwarding task to peer",
            extra={
                "event": "peer_forward",
                "peer_id": peer.node_id,
                "task": task_name,
                "routing_key": routing_key,
                "correlation_id": correlation_id,
            },
        )

        async def attempt() -> Message:
            remaining = deadline.remaining()
            if remaining <= 0:
                raise DeadlineExceeded("request deadline exceeded before peer forward")
            request = Message.new_request(
                sender_id=self.local_node_id,
                correlation_id=correlation_id,
                msg_type=MessageType.FORWARDED_REQUEST,
                payload=encode_forwarded_request(
                    task_name=task_name,
                    payload=payload,
                    routing_key=routing_key,
                    origin_node_id=origin_node_id,
                    remaining_timeout_ms=max(1, int(remaining * 1000)),
                ),
            )
            return await breaker.call(
                lambda: self._exchange_endpoint(
                    peer.host,
                    peer.port,
                    request,
                    timeout_seconds=deadline.remaining(),
                )
            )

        try:
            response = await retry_async(
                attempt,
                policy=self.retry_policy,
                should_retry=lambda exc: isinstance(exc, _RETRYABLE)
                and not isinstance(exc, CircuitOpenError),
                deadline=deadline,
            )
        except (CircuitOpenError, DeadlineExceeded):
            logger.warning(
                "peer forward failed",
                extra={"event": "peer_forward_failed", "peer_id": peer.node_id},
            )
            raise
        except _RETRYABLE as exc:
            logger.warning(
                "peer forward failed",
                extra={"event": "peer_forward_failed", "peer_id": peer.node_id},
            )
            raise PeerTransportError(f"peer {peer.node_id} transport failed") from exc

        if response.msg_type not in (MessageType.RESPONSE, MessageType.ERROR):
            raise PeerProtocolError(f"expected task RESPONSE/ERROR, got {response.msg_type.name}")
        decoded = decode_task_response(response.payload)
        if not decoded.success:
            raise PeerApplicationError(decoded.error_code, decoded.error_message)
        return decoded.result
