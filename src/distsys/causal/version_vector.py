"""Immutable vector-clock causal frontier."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from distsys.causal.actor import CausalActor
from distsys.causal.dot import Dot


class VersionRelation(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    EQUAL = "equal"
    CONCURRENT = "concurrent"


class VersionVector:
    """Immutable vector clock indexed by incarnation-scoped causal actors."""

    __slots__ = ("_entries",)

    def __init__(self, entries: Mapping[CausalActor, int] | None = None) -> None:
        normalized: list[tuple[CausalActor, int]] = []
        for actor, counter in (entries or {}).items():
            if counter < 0:
                raise ValueError("version counters must be non-negative")
            if counter:
                normalized.append((actor, int(counter)))
        self._entries = tuple(sorted(normalized, key=lambda item: item[0]))

    def __repr__(self) -> str:
        inner = ", ".join(f"{actor.wire_key()}: {counter}" for actor, counter in self._entries)
        return f"VersionVector({{{inner}}})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VersionVector):
            return NotImplemented
        return self._entries == other._entries

    def __hash__(self) -> int:
        return hash(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    def get(self, actor: CausalActor) -> int:
        for existing, counter in self._entries:
            if existing == actor:
                return counter
        return 0

    def items(self) -> tuple[tuple[CausalActor, int], ...]:
        return self._entries

    def with_dot(self, dot: Dot) -> VersionVector:
        entries = dict(self._entries)
        entries[dot.actor] = max(entries.get(dot.actor, 0), dot.counter)
        return VersionVector(entries)

    def merge(self, other: VersionVector) -> VersionVector:
        actors = {actor for actor, _ in self._entries} | {actor for actor, _ in other._entries}
        return VersionVector({actor: max(self.get(actor), other.get(actor)) for actor in actors})

    def compare(self, other: VersionVector) -> VersionRelation:
        actors = {actor for actor, _ in self._entries} | {actor for actor, _ in other._entries}
        less = False
        greater = False
        for actor in actors:
            left = self.get(actor)
            right = other.get(actor)
            if left < right:
                less = True
            elif left > right:
                greater = True
            if less and greater:
                return VersionRelation.CONCURRENT
        if less:
            return VersionRelation.BEFORE
        if greater:
            return VersionRelation.AFTER
        return VersionRelation.EQUAL

    def dominates(self, other: VersionVector) -> bool:
        return self.compare(other) in (VersionRelation.AFTER, VersionRelation.EQUAL)

    def concurrent_with(self, other: VersionVector) -> bool:
        return self.compare(other) is VersionRelation.CONCURRENT

    def missing_from(self, required: VersionVector) -> dict[CausalActor, tuple[int, int]]:
        missing: dict[CausalActor, tuple[int, int]] = {}
        for actor, required_counter in required.items():
            local_counter = self.get(actor)
            if local_counter < required_counter:
                missing[actor] = (local_counter + 1, required_counter)
        return missing
