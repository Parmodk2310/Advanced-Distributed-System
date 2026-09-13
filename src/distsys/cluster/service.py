"""Cluster bootstrap, control-plane dispatch, and background lifecycle."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from distsys.cluster.cluster_router import ClusterRouter
from distsys.cluster.codec import (
    AckData,
    decode_gossip,
    decode_join_request,
    decode_ping,
    decode_ping_request,
    encode_ack,
    encode_join_response,
)
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.failure_detector import FailureDetector
from distsys.cluster.gossip import GossipLoop
from distsys.cluster.member import ClusterMember, MemberStatus, SeedAddress, fresh_incarnation
from distsys.cluster.membership import MembershipTable
from distsys.cluster.peer_client import PeerClient
from distsys.protocol.message import Message, MessageType
from distsys.resilience.deadline import Deadline
from distsys.resilience.retry import RetryPolicy
from distsys.utils.config import Settings

logger = logging.getLogger("distsys.cluster.service")


class ClusterBootstrapError(ConnectionError):
    """Raised when a configured node cannot reach any seed."""


class ClusterPeerClient(Protocol):
    async def join(
        self,
        seed: SeedAddress,
        local_member: ClusterMember,
        *,
        timeout_seconds: float,
    ) -> tuple[ClusterMember, ...]: ...

    async def ping(
        self,
        peer: ClusterMember,
        gossip: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData: ...

    async def ping_request(
        self,
        helper: ClusterMember,
        target: ClusterMember,
        gossip: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData: ...

    async def gossip(
        self,
        peer: ClusterMember,
        members: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData: ...

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


class ClusterService:
    def __init__(
        self,
        *,
        settings: Settings,
        bound_port: int,
        execute_local: Callable[[str, Any, Deadline], Awaitable[Any]],
        peer_client: ClusterPeerClient | None = None,
        incarnation: int | None = None,
    ) -> None:
        self.settings = settings
        self.local_member = ClusterMember(
            node_id=settings.node_id,
            host=settings.host,
            port=bound_port,
            status=MemberStatus.ALIVE,
            incarnation=incarnation or fresh_incarnation(),
        )
        self.membership = MembershipTable(
            self.local_member,
            suspicion_timeout_seconds=settings.cluster_suspicion_timeout_seconds,
            dead_retention_seconds=settings.cluster_dead_retention_seconds,
        )
        self.ring = ConsistentHashRing(virtual_nodes=settings.cluster_virtual_nodes)
        self.peer_client: ClusterPeerClient = peer_client or PeerClient(
            local_node_id=settings.node_id,
            retry_policy=RetryPolicy(
                max_attempts=settings.retry_max_attempts,
                base_delay_seconds=settings.retry_base_delay_seconds,
                max_delay_seconds=settings.retry_max_delay_seconds,
            ),
            circuit_breaker_failure_threshold=settings.circuit_breaker_failure_threshold,
            circuit_breaker_recovery_seconds=settings.circuit_breaker_recovery_seconds,
            max_frame_size=settings.max_frame_size,
        )
        self.router = ClusterRouter(
            local_node_id=settings.node_id,
            ring=self.ring,
            peer_client=self.peer_client,
            execute_local=execute_local,
        )
        self._ring_version = -1
        self._background_tasks: set[asyncio.Task[None]] = set()
        self.failure_detector = FailureDetector(
            table=self.membership,
            peer_client=self.peer_client,
            local_node_id=settings.node_id,
            probe_interval_seconds=settings.cluster_probe_interval_seconds,
            ping_timeout_seconds=settings.cluster_ping_timeout_seconds,
            indirect_timeout_seconds=settings.cluster_indirect_timeout_seconds,
            indirect_probe_count=settings.cluster_indirect_probe_count,
            on_membership_change=self.sync_ring,
        )
        self.gossip_loop = GossipLoop(
            table=self.membership,
            peer_client=self.peer_client,
            local_node_id=settings.node_id,
            interval_seconds=settings.cluster_gossip_interval_seconds,
            timeout_seconds=settings.cluster_ping_timeout_seconds,
            on_membership_change=self.sync_ring,
        )

    async def sync_ring(self) -> None:
        version = self.membership.version
        if version == self._ring_version:
            return
        snapshot = await self.membership.snapshot()
        self.ring.rebuild(snapshot)
        self._ring_version = version
        logger.info(
            "cluster membership changed",
            extra={
                "event": "membership_changed",
                "node_id": self.settings.node_id,
                "membership_version": version,
                "alive_members": sum(member.status is MemberStatus.ALIVE for member in snapshot),
            },
        )

    async def bootstrap(self) -> None:
        await self.sync_ring()
        if not self.settings.cluster_seeds:
            return
        candidates = [
            seed
            for seed in self.settings.cluster_seeds
            if not (seed.host == self.local_member.host and seed.port == self.local_member.port)
        ]
        if not candidates:
            raise ClusterBootstrapError("configured cluster seeds contain only the local node")
        failures: list[BaseException] = []
        for seed in candidates:
            try:
                snapshot = await self.peer_client.join(
                    seed,
                    self.local_member,
                    timeout_seconds=self.settings.cluster_ping_timeout_seconds,
                )
            except (ConnectionError, TimeoutError, OSError) as exc:
                failures.append(exc)
                continue
            await self.membership.merge(snapshot)
            await self.sync_ring()
            logger.info(
                "joined cluster through seed",
                extra={
                    "event": "cluster_joined",
                    "node_id": self.settings.node_id,
                    "seed": f"{seed.host}:{seed.port}",
                },
            )
            return
        raise ClusterBootstrapError("unable to contact any configured cluster seed") from failures[
            -1
        ]

    def _response(self, request: Message, msg_type: MessageType, payload: bytes) -> Message:
        return Message.new_response(
            sender_id=self.settings.node_id,
            correlation_id=request.correlation_id,
            msg_type=msg_type,
            payload=payload,
        )

    async def handle_control(self, message: Message) -> Message:
        if message.msg_type is MessageType.JOIN_REQUEST:
            joining = decode_join_request(message.payload)
            await self.membership.merge((joining,))
            await self.sync_ring()
            return self._response(
                message,
                MessageType.JOIN_RESPONSE,
                encode_join_response(await self.membership.snapshot()),
            )

        if message.msg_type is MessageType.PING:
            incoming = decode_ping(message.payload)
            await self.membership.merge(incoming)
            await self.sync_ring()
            snapshot = await self.membership.snapshot()
            return self._response(
                message,
                MessageType.ACK,
                encode_ack(
                    success=True,
                    target_node_id=self.settings.node_id,
                    gossip=snapshot,
                ),
            )

        if message.msg_type is MessageType.PING_REQ:
            target, incoming = decode_ping_request(message.payload)
            await self.membership.merge(incoming)
            await self.sync_ring()
            snapshot = await self.membership.snapshot()
            success = False
            try:
                ack = await self.peer_client.ping(
                    target,
                    snapshot,
                    timeout_seconds=self.settings.cluster_ping_timeout_seconds,
                )
            except (ConnectionError, TimeoutError, OSError):
                ack = None
            if ack is not None and ack.success and ack.target_node_id == target.node_id:
                success = True
                if await self.membership.merge(ack.gossip):
                    await self.sync_ring()
            snapshot = await self.membership.snapshot()
            return self._response(
                message,
                MessageType.ACK,
                encode_ack(
                    success=success,
                    target_node_id=target.node_id,
                    gossip=snapshot,
                ),
            )

        if message.msg_type is MessageType.GOSSIP:
            incoming = decode_gossip(message.payload)
            await self.membership.merge(incoming)
            await self.sync_ring()
            snapshot = await self.membership.snapshot()
            return self._response(
                message,
                MessageType.ACK,
                encode_ack(
                    success=True,
                    target_node_id=self.settings.node_id,
                    gossip=snapshot,
                ),
            )

        raise ValueError(f"unsupported cluster control message: {message.msg_type.name}")

    async def start(self) -> None:
        await self.bootstrap()
        self._background_tasks = {
            asyncio.create_task(
                self.failure_detector.run(),
                name=f"{self.settings.node_id}-failure-detector",
            ),
            asyncio.create_task(
                self.gossip_loop.run(),
                name=f"{self.settings.node_id}-gossip",
            ),
        }

    async def stop(self) -> None:
        tasks = list(self._background_tasks)
        self._background_tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
