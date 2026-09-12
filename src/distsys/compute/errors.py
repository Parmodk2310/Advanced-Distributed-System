"""Typed compute-layer failures."""


class TaskValidationError(ValueError):
    """Raised when an application task receives an invalid payload."""


class WorkerPoolClosedError(RuntimeError):
    """Raised when work is submitted after the worker pool is closed."""


class WorkerPoolBrokenError(RuntimeError):
    """Raised when the process pool can no longer execute work."""


class WorkerPoolSaturatedError(RuntimeError):
    """Raised when the bounded CPU submission capacity is full."""
