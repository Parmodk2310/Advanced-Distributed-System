"""Token-bucket request rate limiting."""

from __future__ import annotations

import time
from collections.abc import Callable


class TokenBucketRateLimiter:
    def __init__(
        self,
        *,
        rate_per_second: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be greater than zero")
        if burst < 1:
            raise ValueError("burst must be at least 1")
        self.rate_per_second = float(rate_per_second)
        self.burst = float(burst)
        self._clock = clock
        self._tokens = float(burst)
        self._last_refill = clock()

    @property
    def available_tokens(self) -> float:
        self._refill()
        return self._tokens

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        self._last_refill = now
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate_per_second)

    def allow(self, cost: float = 1.0) -> bool:
        if cost <= 0:
            raise ValueError("cost must be greater than zero")
        self._refill()
        if self._tokens < cost:
            return False
        self._tokens -= cost
        return True
