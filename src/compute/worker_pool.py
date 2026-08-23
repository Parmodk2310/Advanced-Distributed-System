"""Multiprocessing worker pool for CPU-bound tasks."""

import asyncio
import multiprocessing as mp
from typing import Callable, Any
from concurrent.futures import ProcessPoolExecutor


class CPUIntensiveTask:
    @staticmethod
    def compute_hash(data: bytes, iterations: int = 100000) -> str:
        import hashlib
        result = data if isinstance(data, bytes) else str(data).encode()
        for _ in range(iterations):
            result = hashlib.sha256(result).digest()
        return hashlib.sha256(result).hexdigest()
    
    @staticmethod
    def sort_large_dataset(data):
        return sorted(data)
    
    @staticmethod
    def aggregate_metrics(batch):
        from collections import defaultdict
        result = defaultdict(lambda: {'sum': 0, 'count': 0, 'min': float('inf'), 'max': float('-inf')})
        for item in batch:
            for key, value in item.items():
                if isinstance(value, (int, float)):
                    result[key]['sum'] += value
                    result[key]['count'] += 1
                    result[key]['min'] = min(result[key]['min'], value)
                    result[key]['max'] = max(result[key]['max'], value)
        for key in result:
            if result[key]['count'] > 0:
                result[key]['avg'] = result[key]['sum'] / result[key]['count']
        return dict(result)


class WorkerPool:
    def __init__(self, max_workers=None):
        self.max_workers = max_workers or max(2, mp.cpu_count() - 1)
        self.executor = ProcessPoolExecutor(max_workers=self.max_workers)
        self.pending_tasks = 0
        self.max_pending = self.max_workers * 4
        self._semaphore = asyncio.Semaphore(self.max_pending)
        self._lock = asyncio.Lock()
        
    async def submit(self, fn: Callable, *args, **kwargs) -> Any:
        async with self._semaphore:
            async with self._lock:
                self.pending_tasks += 1
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(self.executor, fn, *args, **kwargs)
            finally:
                async with self._lock:
                    self.pending_tasks -= 1
    
    @property
    def load(self) -> float:
        return self.pending_tasks / self.max_pending
    
    def shutdown(self):
        self.executor.shutdown(wait=True)