"""Deterministic bounded admission control."""

from __future__ import annotations

import asyncio


class BackpressureController:
    def __init__(self, *, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self._in_flight = 0
        self._lock = asyncio.Lock()

    @property
    def in_flight(self) -> int:
        return self._in_flight

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self._in_flight >= self.capacity:
                return False
            self._in_flight += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            if self._in_flight <= 0:
                raise RuntimeError("backpressure release underflow")
            self._in_flight -= 1
