"""Explicit execution classification for registered tasks."""

from __future__ import annotations

from enum import Enum


class ExecutionClass(str, Enum):
    ASYNC = "async"
    CPU = "cpu"


class TaskClassifier:
    """Maps task names to execution classes.

    Unknown names intentionally default to ASYNC so the TaskRouter remains
    responsible for producing the canonical unknown-task error.
    """

    def __init__(self) -> None:
        self._mapping: dict[str, ExecutionClass] = {}

    @classmethod
    def default(cls) -> TaskClassifier:
        classifier = cls()
        classifier.register("echo", ExecutionClass.ASYNC)
        for name in ("hash", "sort", "aggregate"):
            classifier.register(name, ExecutionClass.CPU)
        return classifier

    def register(self, task_name: str, execution_class: ExecutionClass) -> None:
        if not task_name:
            raise ValueError("task name cannot be empty")
        self._mapping[task_name] = execution_class

    def classify(self, task_name: str) -> ExecutionClass:
        return self._mapping.get(task_name, ExecutionClass.ASYNC)
