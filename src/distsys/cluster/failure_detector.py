"""SWIM-lite direct/indirect probing and suspicion transitions."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Protocol

from distsys.cluster.codec import AckData
from distsys.cluster.member import ClusterMember
from distsys.cluster.membership import MembershipTable


class ProbePeerClient(Protocol):
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


class FailureDetector:
    def __init__(
        self,
        *,
        table: MembershipTable,
        peer_client: ProbePeerClient,
        local_node_id: str,
        probe_interval_seconds: float,
        ping_timeout_seconds: float,
        indirect_timeout_seconds: float,
        indirect_probe_count: int,
        on_membership_change: Callable[[], Awaitable[None]],
        choose: Callable[[list[ClusterMember]], ClusterMember] = random.choice,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.table = table
        self.peer_client = peer_client
        self.local_node_id = local_node_id
        self.probe_interval_seconds = probe_interval_seconds
        self.ping_timeout_seconds = ping_timeout_seconds
        self.indirect_timeout_seconds = indirect_timeout_seconds
        self.indirect_probe_count = indirect_probe_count
        self.on_membership_change = on_membership_change
        self.choose = choose
        self.sleep = sleep

    async def run_once(self) -> None:
        if await self.table.advance_timeouts_and_purge():
            await self.on_membership_change()

        candidates = await self.table.probe_candidates()
        if not candidates:
            return
        target = self.choose(list(candidates))
        snapshot = await self.table.snapshot()

        try:
            ack = await self.peer_client.ping(
                target,
                snapshot,
                timeout_seconds=self.ping_timeout_seconds,
            )
        except (ConnectionError, TimeoutError, OSError):
            ack = None

        if ack is not None and ack.success and ack.target_node_id == target.node_id:
            if await self.table.merge(ack.gossip):
                await self.on_membership_change()
            return

        helpers = [
            member
            for member in await self.table.alive_members(include_self=False)
            if member.node_id != target.node_id
        ][: self.indirect_probe_count]

        async def indirect(helper: ClusterMember) -> AckData | None:
            try:
                return await self.peer_client.ping_request(
                    helper,
                    target,
                    snapshot,
                    timeout_seconds=self.indirect_timeout_seconds,
                )
            except (ConnectionError, TimeoutError, OSError):
                return None

        results = await asyncio.gather(*(indirect(helper) for helper in helpers))
        successful = next(
            (
                result
                for result in results
                if result is not None and result.success and result.target_node_id == target.node_id
            ),
            None,
        )
        if successful is not None:
            if await self.table.merge(successful.gossip):
                await self.on_membership_change()
            return

        if await self.table.mark_suspect(target.node_id):
            await self.on_membership_change()

    async def run(self) -> None:
        while True:
            await self.run_once()
            await self.sleep(self.probe_interval_seconds)
