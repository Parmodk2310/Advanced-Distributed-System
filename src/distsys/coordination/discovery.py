"""Discovery of identity-aware Phase-5 cluster seeds from coordination metadata."""

from __future__ import annotations

from distsys.cluster.member import SeedAddress
from distsys.coordination.client import CoordinationClient


class DiscoveryService:
    def __init__(self, client: CoordinationClient) -> None:
        self.client = client

    async def discover_seeds(self, local_node_id: str) -> tuple[SeedAddress, ...]:
        members = await self.client.discover_members()
        return tuple(
            SeedAddress(member.host, member.port, member.node_id)
            for member in sorted(members, key=lambda item: item.node_id)
            if member.node_id != local_node_id
        )
