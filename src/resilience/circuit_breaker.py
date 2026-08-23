"""Circuit breaker pattern for fault isolation."""

import asyncio
import time
import logging
from typing import Callable, Any
from enum import Enum, auto

logger = logging.getLogger("DistSys")


class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


class CircuitBreakerOpen(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 10.0, half_open_max: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes = 0
        self._last_failure_time = 0.0
        self._half_open_count = 0
        self._lock = asyncio.Lock()
        
    @property
    def state(self) -> CircuitState:
        return self._state
    
    async def call(self, coro_factory: Callable, *args, **kwargs) -> Any:
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_count = 0
                    logger.info("Circuit HALF_OPEN")
                else:
                    raise CircuitBreakerOpen("Circuit OPEN")
            if self._state == CircuitState.HALF_OPEN and self._half_open_count >= self.half_open_max:
                raise CircuitBreakerOpen("HALF_OPEN limit")
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_count += 1
        try:
            result = await coro_factory(*args, **kwargs)
            await self._on_success()
            return result
        except Exception:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._successes += 1
                if self._successes >= self.half_open_max:
                    self._state = CircuitState.CLOSED
                    self._failures = 0
                    self._successes = 0
                    logger.info("Circuit CLOSED")
            else:
                self._failures = max(0, self._failures - 1)
    
    async def _on_failure(self):
        async with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit OPEN - recovery failed")
            elif self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit OPEN after {self._failures} failures")