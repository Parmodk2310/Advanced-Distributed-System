"""Bounded CPU worker-pool isolation built on ProcessPoolExecutor."""

from __future__ import annotations

import asyncio
import multiprocessing
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any

from distsys.compute.errors import (
    WorkerPoolBrokenError,
    WorkerPoolClosedError,
    WorkerPoolSaturatedError,
)


class _PendingLimiter:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._in_flight = 0
        self._lock = threading.Lock()

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight

    def try_acquire(self) -> bool:
        with self._lock:
            if self._in_flight >= self.capacity:
                return False
            self._in_flight += 1
            return True

    def release(self) -> None:
        with self._lock:
            if self._in_flight <= 0:
                return
            self._in_flight -= 1


class WorkerPool:
    def __init__(self, *, max_workers: int = 2, max_pending: int = 200) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if max_pending < 1:
            raise ValueError("max_pending must be at least 1")
        self.max_workers = max_workers
        self.max_pending = max_pending
        self._executor: ProcessPoolExecutor | None = None
        self._closed = False
        self._pending = _PendingLimiter(max_pending)

    @property
    def started(self) -> bool:
        return self._executor is not None and not self._closed

    @property
    def pending_count(self) -> int:
        return self._pending.in_flight

    async def start(self) -> None:
        if self._closed:
            raise WorkerPoolClosedError("worker pool is closed")
        if self._executor is None:
            self._executor = ProcessPoolExecutor(
                max_workers=self.max_workers,
                mp_context=multiprocessing.get_context("spawn"),
            )

    async def execute(self, fn: Callable[..., Any], *args: Any) -> Any:
        if self._closed:
            raise WorkerPoolClosedError("worker pool is closed")
        if self._executor is None:
            await self.start()
        assert self._executor is not None

        if not self._pending.try_acquire():
            raise WorkerPoolSaturatedError("worker pool pending capacity is full")

        try:
            concurrent_future = self._executor.submit(fn, *args)
        except BrokenProcessPool as exc:
            self._pending.release()
            raise WorkerPoolBrokenError("worker pool is broken") from exc
        except Exception:
            self._pending.release()
            raise

        concurrent_future.add_done_callback(lambda _: self._pending.release())
        wrapped = asyncio.wrap_future(concurrent_future)
        try:
            return await wrapped
        except BrokenProcessPool as exc:
            raise WorkerPoolBrokenError("worker pool is broken") from exc

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        executor = self._executor
        self._executor = None
        if executor is not None:
            await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)
