"""Concurrency-safe local causal clock."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from distsys.causal.actor import CausalActor
from distsys.causal.dot import Dot
from distsys.causal.version_vector import VersionVector


@dataclass(slots=True)
class CausalAllocation:
    dot: Dot
    frontier: VersionVector
    _committed: bool = False

    def commit(self) -> None:
        self._committed = True


@dataclass(slots=True)
class CausalObservation:
    frontier: VersionVector
    _committed: bool = False

    def commit(self) -> None:
        self._committed = True


class CausalClock:
    """Maintains one actor-local counter plus observed causal knowledge."""

    def __init__(self, actor: CausalActor) -> None:
        self.actor = actor
        self._frontier = VersionVector()
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def staged_observe(self, version: VersionVector) -> AsyncIterator[CausalObservation]:
        await self._lock.acquire()
        try:
            observation = CausalObservation(self._frontier.merge(version))
            yield observation
            if observation._committed:
                self._frontier = observation.frontier
        finally:
            self._lock.release()

    async def observe(self, version: VersionVector) -> VersionVector:
        async with self.staged_observe(version) as observation:
            observation.commit()
            return observation.frontier

    async def restore(self, version: VersionVector) -> VersionVector:
        """Restore a durable frontier exactly for this clock actor."""
        async with self._lock:
            self._frontier = version
            return self._frontier

    @asynccontextmanager
    async def staged_allocation(
        self,
        observed: VersionVector | None = None,
    ) -> AsyncIterator[CausalAllocation]:
        await self._lock.acquire()
        try:
            base = self._frontier
            if observed is not None:
                base = base.merge(observed)
            counter = base.get(self.actor) + 1
            dot = Dot(self.actor, counter)
            allocation = CausalAllocation(dot=dot, frontier=base.with_dot(dot))
            yield allocation
            if allocation._committed:
                self._frontier = allocation.frontier
        finally:
            self._lock.release()

    async def allocate(
        self,
        observed: VersionVector | None = None,
    ) -> tuple[Dot, VersionVector]:
        async with self.staged_allocation(observed) as allocation:
            allocation.commit()
            return allocation.dot, allocation.frontier

    async def frontier(self) -> VersionVector:
        async with self._lock:
            return self._frontier
