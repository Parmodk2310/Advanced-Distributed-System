"""Concurrency-safe local causal clock."""

from __future__ import annotations

import asyncio

from distsys.causal.actor import CausalActor
from distsys.causal.dot import Dot
from distsys.causal.version_vector import VersionVector


class CausalClock:
    """Maintains one actor-local counter plus observed causal knowledge."""

    def __init__(self, actor: CausalActor) -> None:
        self.actor = actor
        self._frontier = VersionVector()
        self._lock = asyncio.Lock()

    async def observe(self, version: VersionVector) -> VersionVector:
        async with self._lock:
            self._frontier = self._frontier.merge(version)
            return self._frontier

    async def allocate(
        self,
        observed: VersionVector | None = None,
    ) -> tuple[Dot, VersionVector]:
        async with self._lock:
            if observed is not None:
                self._frontier = self._frontier.merge(observed)
            counter = self._frontier.get(self.actor) + 1
            dot = Dot(self.actor, counter)
            self._frontier = self._frontier.with_dot(dot)
            return dot, self._frontier

    async def frontier(self) -> VersionVector:
        async with self._lock:
            return self._frontier
