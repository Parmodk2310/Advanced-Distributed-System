import asyncio
import threading

import pytest

from distsys.persistence.errors import PersistenceBackpressureError
from distsys.persistence.executor import PersistenceExecutor
from distsys.resilience.deadline import Deadline


@pytest.mark.asyncio
async def test_executor_runs_blocking_callable_off_event_loop_thread():
    loop_thread = threading.get_ident()
    executor = PersistenceExecutor(capacity=1)
    worker_thread = await executor.run(threading.get_ident)
    assert worker_thread != loop_thread


@pytest.mark.asyncio
async def test_executor_backpressures_when_capacity_is_full():
    executor = PersistenceExecutor(capacity=1)
    started = threading.Event()
    release = threading.Event()

    def blocking() -> str:
        started.set()
        release.wait(timeout=2)
        return "done"

    first = asyncio.create_task(executor.run(blocking))
    await asyncio.to_thread(started.wait, 1)

    with pytest.raises(PersistenceBackpressureError):
        await executor.run(lambda: "second", deadline=Deadline.after(0.02))

    release.set()
    assert await first == "done"


@pytest.mark.asyncio
async def test_executor_rejects_invalid_capacity():
    with pytest.raises(ValueError):
        PersistenceExecutor(capacity=0)
