"""Observed-remove set with add-wins semantics for unseen concurrent adds."""

from __future__ import annotations

from collections.abc import Mapping

from distsys.causal import Dot


class ORSet:
    __slots__ = ("_adds", "_removed")

    def __init__(
        self,
        adds: Mapping[str, frozenset[Dot] | set[Dot]] | None = None,
        removed: frozenset[Dot] | set[Dot] | None = None,
    ) -> None:
        normalized: list[tuple[str, frozenset[Dot]]] = []
        for element, dots in (adds or {}).items():
            if not isinstance(element, str):
                raise TypeError("ORSet elements must be strings")
            normalized.append((element, frozenset(dots)))
        self._adds = tuple(sorted(normalized, key=lambda item: item[0]))
        self._removed = frozenset(removed or ())

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, ORSet)
            and self._adds == other._adds
            and self._removed == other._removed
        )

    def __hash__(self) -> int:
        return hash((self._adds, self._removed))

    def additions(self) -> tuple[tuple[str, frozenset[Dot]], ...]:
        return self._adds

    def removed(self) -> frozenset[Dot]:
        return self._removed

    def _add_map(self) -> dict[str, frozenset[Dot]]:
        return dict(self._adds)

    def add(self, element: str, dot: Dot) -> ORSet:
        if not isinstance(element, str):
            raise TypeError("ORSet elements must be strings")
        adds = self._add_map()
        adds[element] = adds.get(element, frozenset()) | {dot}
        return ORSet(adds, self._removed)

    def remove(self, element: str) -> ORSet:
        if not isinstance(element, str):
            raise TypeError("ORSet elements must be strings")
        active = self._add_map().get(element, frozenset()) - self._removed
        return ORSet(self._add_map(), self._removed | active)

    def contains(self, element: str) -> bool:
        return element in self.value()

    def value(self) -> frozenset[str]:
        return frozenset(element for element, dots in self._adds if bool(dots - self._removed))

    def merge(self, other: ORSet) -> ORSet:
        adds: dict[str, frozenset[Dot]] = self._add_map()
        for element, dots in other._adds:
            adds[element] = adds.get(element, frozenset()) | dots
        return ORSet(adds, self._removed | other._removed)

    def to_dict(self) -> dict[str, object]:
        return {
            "adds": {
                element: [
                    {"actor": dot.actor.wire_key(), "counter": dot.counter} for dot in sorted(dots)
                ]
                for element, dots in self._adds
            },
            "removed": [
                {"actor": dot.actor.wire_key(), "counter": dot.counter}
                for dot in sorted(self._removed)
            ],
        }
