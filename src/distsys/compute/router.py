"""Task registration and dispatch."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


class UnknownTaskError(LookupError):
    pass


class TaskRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[Any], Any]] = {}

    def register(self, name: str, handler: Callable[[Any], Any]) -> None:
        if not name:
            raise ValueError("task name cannot be empty")
        if name in self._handlers:
            raise ValueError(f"task already registered: {name}")
        self._handlers[name] = handler

    def resolve(self, name: str) -> Callable[[Any], Any]:
        try:
            return self._handlers[name]
        except KeyError as exc:
            raise UnknownTaskError(name) from exc

    async def dispatch(self, name: str, payload: Any) -> Any:
        handler = self.resolve(name)
        result = handler(payload)
        if inspect.isawaitable(result):
            result = await result
        return result
