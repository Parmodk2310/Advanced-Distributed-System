"""Causal actor identity scoped to a Phase-3 membership incarnation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True, slots=True)
class CausalActor:
    """Uniquely identifies one running incarnation of a physical node."""

    node_id: str
    incarnation: int

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id must not be empty")
        if self.incarnation < 0:
            raise ValueError("incarnation must be non-negative")

    def wire_key(self) -> str:
        return f"{self.node_id}@{self.incarnation}"
