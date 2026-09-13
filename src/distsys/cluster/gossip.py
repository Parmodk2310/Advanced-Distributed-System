"""Best-effort membership gossip dissemination."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Protocol

from distsys.cluster.codec import AckData
from distsys.cluster.member import ClusterMember
from distsys.cluster.membership import MembershipTable

logger = logging.getLogger("distsys.cluster.gossip")


class GossipPeerClient(Protocol):
    async def gossip(
        self,
        peer: ClusterMember,
        members: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData: ...


class GossipLoop:
    def __init__(
        self,
        *,
        table: MembershipTable,
        peer_client: GossipPeerClient,
        local_node_id: str,
        interval_seconds: float,
        timeout_seconds: float,
        on_membership_change: Callable[[], Awaitable[None]],
        choose: Callable[[list[ClusterMember]], ClusterMember] = random.choice,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.table = table
        self.peer_client = peer_client
        self.local_node_id = local_node_id
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.on_membership_change = on_membership_change
        self.choose = choose
        self.sleep = sleep

    async def run_once(self) -> None:
        peers = await self.table.alive_members(include_self=False)
        if not peers:
            return
        peer = self.choose(list(peers))
        snapshot = await self.table.snapshot()
        try:
            ack = await self.peer_client.gossip(
                peer,
                snapshot,
                timeout_seconds=self.timeout_seconds,
            )
        except (ConnectionError, TimeoutError, OSError):
            logger.debug(
                "cluster gossip failed",
                extra={"event": "cluster_gossip_failed", "peer_id": peer.node_id},
            )
            return
        logger.debug(
            "cluster gossip sent",
            extra={
                "event": "cluster_gossip_sent",
                "peer_id": peer.node_id,
                "member_count": len(snapshot),
            },
        )
        if await self.table.merge(ack.gossip):
            await self.on_membership_change()

    async def run(self) -> None:
        while True:
            await self.run_once()
            await self.sleep(self.interval_seconds)
