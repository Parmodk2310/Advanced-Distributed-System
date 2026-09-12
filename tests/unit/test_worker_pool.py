import asyncio
import time

import pytest

from distsys.compute.errors import WorkerPoolClosedError, WorkerPoolSaturatedError
from distsys.compute.worker_pool import WorkerPool


@pytest.mark.asyncio
async def test_worker_pool_executes_picklable_cpu_function():
    pool = WorkerPool(max_workers=2)
    await pool.start()
    try:
        assert await pool.execute(pow, 2, 10) == 1024
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_worker_pool_rejects_work_after_close():
    pool = WorkerPool(max_workers=1)
    await pool.start()
    await pool.close()

    with pytest.raises(WorkerPoolClosedError):
        await pool.execute(pow, 2, 3)


def test_worker_pool_rejects_invalid_worker_count():
    with pytest.raises(ValueError, match="max_workers"):
        WorkerPool(max_workers=0)


@pytest.mark.asyncio
async def test_worker_pool_keeps_pending_slot_until_process_work_finishes():
    pool = WorkerPool(max_workers=1, max_pending=1)
    await pool.start()
    try:
        first = asyncio.create_task(pool.execute(time.sleep, 0.2))
        await asyncio.sleep(0.02)

        with pytest.raises(WorkerPoolSaturatedError):
            await pool.execute(pow, 2, 3)

        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

        # Cancellation of the waiter must not free the process slot early.
        with pytest.raises(WorkerPoolSaturatedError):
            await pool.execute(pow, 2, 3)

        for _ in range(60):
            if pool.pending_count == 0:
                break
            await asyncio.sleep(0.05)
        assert pool.pending_count == 0
        assert await pool.execute(pow, 2, 3) == 8
    finally:
        await pool.close()
