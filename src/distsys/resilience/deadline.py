"""Monotonic request deadlines."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class DeadlineExceeded(TimeoutError):
    """Raised when a request has exhausted its time budget."""


@dataclass(slots=True, frozen=True)
class Deadline:
    _expires_at: float
    _clock: Callable[[], float] = time.monotonic

    @classmethod
    def after(
        cls,
        seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> Deadline:
        if seconds <= 0:
            raise ValueError("deadline seconds must be greater than zero")
        return cls(clock() + seconds, clock)

    def remaining(self) -> float:
        return max(0.0, self._expires_at - self._clock())

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    async def run(self, awaitable: Awaitable[T]) -> T:
        timeout = self.remaining()
        if timeout <= 0.0:
            if hasattr(awaitable, "close"):
                awaitable.close()  # type: ignore[attr-defined]
            raise DeadlineExceeded("request deadline exceeded")
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout)
        except TimeoutError as exc:
            raise DeadlineExceeded("request deadline exceeded") from exc
