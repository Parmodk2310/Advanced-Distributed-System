"""Keyed task ownership and deterministic candidate failover."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember
from distsys.cluster.peer_client import PeerApplicationError, PeerTransportError
from distsys.proto import messages_pb2
from distsys.resilience.circuit_breaker import CircuitOpenError
from distsys.resilience.deadline import Deadline, DeadlineExceeded

logger = logging.getLogger("distsys.cluster.cluster_router")


class ForwardTaskPeer(Protocol):
    async def forward_task(
        self,
        peer: ClusterMember,
        *,
        task_name: str,
        payload: Any,
        routing_key: str,
        origin_node_id: str,
        deadline: Deadline,
    ) -> Any: ...


class LocalOverloadedError(RuntimeError):
    """Raised when local execution capacity is unavailable."""


class PeerUnavailableError(ConnectionError):
    """Raised when every usable routing candidate fails."""


class ClusterRouter:
    def __init__(
        self,
        *,
        local_node_id: str,
        ring: ConsistentHashRing,
        peer_client: ForwardTaskPeer,
        execute_local: Callable[[str, Any, Deadline], Awaitable[Any]],
    ) -> None:
        self.local_node_id = local_node_id
        self.ring = ring
        self.peer_client = peer_client
        self.execute_local = execute_local

    async def execute(
        self,
        task_name: str,
        payload: Any,
        *,
        routing_key: str,
        deadline: Deadline,
    ) -> Any:
        candidates = self.ring.candidates(routing_key)
        saw_retryable_candidate_failure = False

        for candidate in candidates:
            if deadline.expired():
                raise DeadlineExceeded("request deadline exceeded during cluster routing")

            if candidate.node_id == self.local_node_id:
                try:
                    return await self.execute_local(task_name, payload, deadline)
                except LocalOverloadedError:
                    saw_retryable_candidate_failure = True
                    logger.info(
                        "routing candidate failed over",
                        extra={
                            "event": "route_failover",
                            "from_node_id": candidate.node_id,
                            "routing_key": routing_key,
                            "reason": "local_overloaded",
                        },
                    )
                    continue

            try:
                return await self.peer_client.forward_task(
                    candidate,
                    task_name=task_name,
                    payload=payload,
                    routing_key=routing_key,
                    origin_node_id=self.local_node_id,
                    deadline=deadline,
                )
            except (PeerTransportError, CircuitOpenError) as exc:
                saw_retryable_candidate_failure = True
                logger.info(
                    "routing candidate failed over",
                    extra={
                        "event": "route_failover",
                        "from_node_id": candidate.node_id,
                        "routing_key": routing_key,
                        "reason": type(exc).__name__,
                    },
                )
                continue
            except PeerApplicationError as exc:
                if exc.code in (messages_pb2.OVERLOADED, messages_pb2.RATE_LIMITED):
                    saw_retryable_candidate_failure = True
                    logger.info(
                        "routing candidate failed over",
                        extra={
                            "event": "route_failover",
                            "from_node_id": candidate.node_id,
                            "routing_key": routing_key,
                            "reason": f"application_error_{exc.code}",
                        },
                    )
                    continue
                raise

        if saw_retryable_candidate_failure:
            raise PeerUnavailableError("all cluster routing candidates are unavailable")
        raise PeerUnavailableError("no usable cluster routing candidate")
