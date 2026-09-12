import pytest

from distsys.compute.classification import ExecutionClass, TaskClassifier


def test_default_classifier_marks_known_cpu_tasks():
    classifier = TaskClassifier.default()

    assert classifier.classify("echo") is ExecutionClass.ASYNC
    assert classifier.classify("hash") is ExecutionClass.CPU
    assert classifier.classify("sort") is ExecutionClass.CPU
    assert classifier.classify("aggregate") is ExecutionClass.CPU


def test_unknown_task_defaults_to_async_for_router_validation():
    classifier = TaskClassifier.default()
    assert classifier.classify("does-not-exist") is ExecutionClass.ASYNC


def test_register_rejects_empty_task_name():
    classifier = TaskClassifier()
    with pytest.raises(ValueError, match="task name cannot be empty"):
        classifier.register("", ExecutionClass.CPU)
