"""Bounded bridge from asyncio request paths to blocking persistence work."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

from distsys.persistence.errors import PersistenceBackpressureError
from distsys.resilience.deadline import Deadline, DeadlineExceeded

T = TypeVar("T")


class PersistenceExecutor:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._capacity = capacity
        self._semaphore = asyncio.Semaphore(capacity)
        self._in_flight = 0
        self._state_lock = asyncio.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def in_flight(self) -> int:
        return self._in_flight

    async def _acquire(self, deadline: Deadline | None) -> None:
        try:
            if deadline is None:
                await self._semaphore.acquire()
            else:
                await deadline.run(self._semaphore.acquire())
        except DeadlineExceeded as exc:
            raise PersistenceBackpressureError("persistence admission deadline exceeded") from exc
        async with self._state_lock:
            self._in_flight += 1

    async def run(self, fn: Callable[[], T], deadline: Deadline | None = None) -> T:
        await self._acquire(deadline)
        try:
            return await asyncio.to_thread(fn)
        finally:
            async with self._state_lock:
                self._in_flight -= 1
            self._semaphore.release()
