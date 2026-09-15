"""Bounded retry for benchmark setup transport operations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_transport(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 5,
    delay_seconds: float = 0.2,
) -> T:
    """Retry transient transport failures outside the measured benchmark window."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")

    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except (ConnectionError, OSError, TimeoutError):
            if attempt == attempts:
                raise
            await asyncio.sleep(delay_seconds * attempt)

    raise AssertionError("unreachable")
