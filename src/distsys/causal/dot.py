"""Dotted causal event identifiers."""

from __future__ import annotations

from dataclasses import dataclass

from distsys.causal.actor import CausalActor


@dataclass(frozen=True, order=True, slots=True)
class Dot:
    """Unique causal event within one causal actor epoch."""

    actor: CausalActor
    counter: int

    def __post_init__(self) -> None:
        if self.counter < 1:
            raise ValueError("counter must be >= 1")
