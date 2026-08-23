"""Adaptive backpressure controller."""

import asyncio
import random
import time


class BackpressureController:
    def __init__(self, max_queue_depth: int = 1000, target_latency: float = 0.1):
        self.max_queue_depth = max_queue_depth
        self.target_latency = target_latency
        self.current_queue_depth = 0
        self.tokens = max_queue_depth
        self.last_refill = time.time()
        self.token_rate = max_queue_depth
        self.rejection_rate = 0.0
        self._lock = asyncio.Lock()
        
    async def acquire(self) -> bool:
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(self.max_queue_depth, self.tokens + elapsed * self.token_rate)
            self.last_refill = now
            queue_ratio = self.current_queue_depth / self.max_queue_depth
            if queue_ratio > 0.9:
                self.rejection_rate = min(1.0, self.rejection_rate + 0.1)
                if random.random() < self.rejection_rate:
                    return False
            elif queue_ratio < 0.5:
                self.rejection_rate = max(0.0, self.rejection_rate - 0.05)
            if self.tokens >= 1:
                self.tokens -= 1
                self.current_queue_depth += 1
                return True
            return False
    
    async def release(self):
        async with self._lock:
            self.current_queue_depth = max(0, self.current_queue_depth - 1)
    
    @property
    def load_factor(self) -> float:
        return self.current_queue_depth / self.max_queue_depth