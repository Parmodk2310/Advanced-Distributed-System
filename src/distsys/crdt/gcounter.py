"""State-based grow-only counter."""

from __future__ import annotations

from collections.abc import Mapping

from distsys.causal import CausalActor


class GCounter:
    __slots__ = ("_components",)

    def __init__(self, components: Mapping[CausalActor, int] | None = None) -> None:
        normalized: list[tuple[CausalActor, int]] = []
        for actor, value in (components or {}).items():
            if value < 0:
                raise ValueError("gcounter components must be non-negative")
            if value:
                normalized.append((actor, int(value)))
        self._components = tuple(sorted(normalized, key=lambda item: item[0]))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, GCounter) and self._components == other._components

    def __hash__(self) -> int:
        return hash(self._components)

    def component(self, actor: CausalActor) -> int:
        for existing, value in self._components:
            if existing == actor:
                return value
        return 0

    def components(self) -> tuple[tuple[CausalActor, int], ...]:
        return self._components

    def increment(self, actor: CausalActor, amount: int = 1) -> GCounter:
        if amount < 1:
            raise ValueError("amount must be >= 1")
        items = dict(self._components)
        items[actor] = items.get(actor, 0) + amount
        return GCounter(items)

    def value(self) -> int:
        return sum(value for _, value in self._components)

    def merge(self, other: GCounter) -> GCounter:
        actors = {actor for actor, _ in self._components} | {
            actor for actor, _ in other._components
        }
        return GCounter(
            {actor: max(self.component(actor), other.component(actor)) for actor in actors}
        )

    def to_dict(self) -> dict[str, object]:
        return {actor.wire_key(): value for actor, value in self._components}
