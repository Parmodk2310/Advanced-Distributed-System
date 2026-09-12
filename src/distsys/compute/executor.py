"""Execution facade that keeps orchestration out of the TCP node."""

from __future__ import annotations

from typing import Any

from distsys.compute.classification import ExecutionClass, TaskClassifier
from distsys.compute.router import TaskRouter
from distsys.compute.worker_pool import WorkerPool
from distsys.resilience.deadline import Deadline


class TaskExecutor:
    def __init__(
        self,
        *,
        router: TaskRouter,
        classifier: TaskClassifier,
        worker_pool: WorkerPool,
    ) -> None:
        self.router = router
        self.classifier = classifier
        self.worker_pool = worker_pool

    async def start(self) -> None:
        await self.worker_pool.start()

    async def close(self) -> None:
        await self.worker_pool.close()

    async def execute(self, task_name: str, payload: Any, *, deadline: Deadline) -> Any:
        execution_class = self.classifier.classify(task_name)
        if execution_class is ExecutionClass.CPU:
            handler = self.router.resolve(task_name)
            return await deadline.run(self.worker_pool.execute(handler, payload))
        return await deadline.run(self.router.dispatch(task_name, payload))
