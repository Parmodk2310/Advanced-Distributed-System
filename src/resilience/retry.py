"""Retry policy with exponential backoff and jitter."""

import random
import asyncio
from typing import Callable, Any


class RetryPolicy:
    def __init__(self, max_retries: int = 3, base_delay: float = 0.1, 
                 max_delay: float = 5.0, exponential_base: float = 2.0, jitter: bool = True):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        
    async def execute(self, coro_factory: Callable, *args, **kwargs) -> Any:
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                return await coro_factory(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (self.exponential_base ** attempt), self.max_delay)
                    if self.jitter:
                        delay *= (0.5 + random.random() * 0.5)
                    await asyncio.sleep(delay)
        raise last_exception