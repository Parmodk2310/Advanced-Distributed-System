"""Asynchronous CLOSED/OPEN/HALF_OPEN circuit breaker."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

T = TypeVar("T")


class CircuitOpenError(ConnectionError):
    """Raised when a circuit breaker refuses a call."""


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        recovery_timeout_seconds: float = 10.0,
        half_open_max_calls: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be greater than zero")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least 1")

        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_max_calls = half_open_max_calls
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def _before_call(self) -> CircuitState:
        async with self._lock:
            if self._state is CircuitState.OPEN:
                assert self._opened_at is not None
                if self._clock() - self._opened_at >= self.recovery_timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_in_flight = 0
                else:
                    raise CircuitOpenError("circuit breaker is open")

            state_at_start = self._state
            if state_at_start is CircuitState.HALF_OPEN:
                if self._half_open_in_flight >= self.half_open_max_calls:
                    raise CircuitOpenError("circuit breaker half-open probe limit reached")
                self._half_open_in_flight += 1
            return state_at_start

    async def _record_success(self, state_at_start: CircuitState) -> None:
        async with self._lock:
            if state_at_start is CircuitState.HALF_OPEN:
                self._half_open_in_flight = max(0, self._half_open_in_flight - 1)
                self._state = CircuitState.CLOSED
                self._opened_at = None
            self._failure_count = 0

    async def _record_failure(self, state_at_start: CircuitState) -> None:
        async with self._lock:
            if state_at_start is CircuitState.HALF_OPEN:
                self._half_open_in_flight = max(0, self._half_open_in_flight - 1)
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                self._failure_count = self.failure_threshold
                return

            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()

    async def call(self, operation: Callable[[], Awaitable[T]]) -> T:
        state_at_start = await self._before_call()
        try:
            result = await operation()
        except Exception:
            await self._record_failure(state_at_start)
            raise
        await self._record_success(state_at_start)
        return result
