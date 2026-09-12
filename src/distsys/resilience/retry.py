"""Deadline-aware asynchronous retry with exponential backoff and full jitter."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from distsys.resilience.deadline import Deadline, DeadlineExceeded


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds cannot be negative")
        if self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds cannot be negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds cannot be less than base_delay_seconds")


async def retry_async[T](
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    should_retry: Callable[[Exception], bool],
    deadline: Deadline | None = None,
    random_fn: Callable[[float, float], float] = random.uniform,
    sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run an async operation with full-jitter retries.

    `max_attempts` includes the initial attempt. Local CPU execution does not use
    this helper in Phase 2; it is provided for future remote/dependency calls.
    """

    for attempt_index in range(policy.max_attempts):
        if deadline is not None and deadline.expired():
            raise DeadlineExceeded("request deadline exceeded before retry attempt")

        try:
            return await operation()
        except Exception as exc:
            is_last = attempt_index + 1 >= policy.max_attempts
            if is_last or not should_retry(exc):
                raise

            cap = min(
                policy.max_delay_seconds,
                policy.base_delay_seconds * (2**attempt_index),
            )
            delay = random_fn(0.0, cap) if cap > 0 else 0.0

            if deadline is not None:
                remaining = deadline.remaining()
                if remaining <= 0.0 or delay >= remaining:
                    raise DeadlineExceeded(
                        "request deadline exceeded during retry backoff"
                    ) from exc

            if delay > 0.0:
                await sleep_fn(delay)

    raise RuntimeError("retry loop exhausted unexpectedly")
