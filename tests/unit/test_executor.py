import pytest

from distsys.compute.classification import ExecutionClass, TaskClassifier
from distsys.compute.executor import TaskExecutor
from distsys.compute.router import TaskRouter
from distsys.compute.tasks import echo_task, sort_task
from distsys.compute.worker_pool import WorkerPool
from distsys.resilience.deadline import Deadline


@pytest.mark.asyncio
async def test_executor_runs_async_task_on_router_path():
    router = TaskRouter()
    router.register("echo", echo_task)
    classifier = TaskClassifier()
    classifier.register("echo", ExecutionClass.ASYNC)
    executor = TaskExecutor(
        router=router,
        classifier=classifier,
        worker_pool=WorkerPool(max_workers=1),
    )
    await executor.start()
    try:
        payload = {"message": "hello"}
        assert await executor.execute("echo", payload, deadline=Deadline.after(1.0)) == payload
    finally:
        await executor.close()


@pytest.mark.asyncio
async def test_executor_runs_cpu_task_in_worker_pool():
    router = TaskRouter()
    router.register("sort", sort_task)
    classifier = TaskClassifier()
    classifier.register("sort", ExecutionClass.CPU)
    executor = TaskExecutor(
        router=router,
        classifier=classifier,
        worker_pool=WorkerPool(max_workers=1),
    )
    await executor.start()
    try:
        assert await executor.execute(
            "sort",
            {"values": [3, 1, 2]},
            deadline=Deadline.after(2.0),
        ) == {"values": [1, 2, 3], "count": 3}
    finally:
        await executor.close()
