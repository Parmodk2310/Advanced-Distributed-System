"""Shared CRDT typing contracts."""

from typing import Protocol, Self


class CRDT(Protocol):
    def merge(self, other: Self) -> Self: ...
    def to_dict(self) -> dict[str, object]: ...
