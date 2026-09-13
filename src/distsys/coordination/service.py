"""Facade for etcd discovery and lease coordination."""

from __future__ import annotations

from distsys.cluster.member import SeedAddress
from distsys.coordination.client import CoordinationClient
from distsys.coordination.discovery import DiscoveryService
from distsys.coordination.lease import LeaseManager
from distsys.coordination.models import CoordinationHealth, CoordinationMember


class CoordinationService:
    def __init__(
        self,
        client: CoordinationClient,
        discovery: DiscoveryService,
        lease_manager: LeaseManager,
    ) -> None:
        self.client = client
        self.discovery = discovery
        self.lease_manager = lease_manager
        self._started = False

    @property
    def health(self) -> CoordinationHealth:
        return self.lease_manager.health

    async def bootstrap(self, member: CoordinationMember) -> tuple[SeedAddress, ...]:
        await self.client.connect()
        await self.client.put_node_metadata(member)
        seeds = await self.discovery.discover_seeds(member.node_id)
        await self.lease_manager.start(member)
        self._started = True
        return seeds

    async def stop(self) -> None:
        if self._started:
            await self.lease_manager.stop()
            self._started = False
        await self.client.close()
