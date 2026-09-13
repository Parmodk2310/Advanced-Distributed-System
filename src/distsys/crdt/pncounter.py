"""Positive/negative counter composed from two GCounters."""

from __future__ import annotations

from dataclasses import dataclass, field

from distsys.causal import CausalActor
from distsys.crdt.gcounter import GCounter


@dataclass(frozen=True, slots=True)
class PNCounter:
    positive: GCounter = field(default_factory=GCounter)
    negative: GCounter = field(default_factory=GCounter)

    def increment(self, actor: CausalActor, amount: int = 1) -> PNCounter:
        return PNCounter(self.positive.increment(actor, amount), self.negative)

    def decrement(self, actor: CausalActor, amount: int = 1) -> PNCounter:
        return PNCounter(self.positive, self.negative.increment(actor, amount))

    def value(self) -> int:
        return self.positive.value() - self.negative.value()

    def merge(self, other: PNCounter) -> PNCounter:
        return PNCounter(
            self.positive.merge(other.positive),
            self.negative.merge(other.negative),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "positive": self.positive.to_dict(),
            "negative": self.negative.to_dict(),
        }
