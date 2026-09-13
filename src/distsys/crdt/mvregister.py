"""State-based multi-value register preserving concurrent values."""

from __future__ import annotations

import json
from collections.abc import Mapping

from distsys.causal import Dot


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class MVRegister:
    __slots__ = ("_superseded", "_values")

    def __init__(
        self,
        values: Mapping[Dot, str] | None = None,
        superseded: frozenset[Dot] | set[Dot] | None = None,
    ) -> None:
        self._values = tuple(sorted((values or {}).items(), key=lambda item: item[0]))
        self._superseded = frozenset(superseded or ())

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, MVRegister)
            and self._values == other._values
            and self._superseded == other._superseded
        )

    def __hash__(self) -> int:
        return hash((self._values, self._superseded))

    def entries(self) -> tuple[tuple[Dot, str], ...]:
        return self._values

    def superseded(self) -> frozenset[Dot]:
        return self._superseded

    def _value_map(self) -> dict[Dot, str]:
        return dict(self._values)

    def write(self, value: object, dot: Dot) -> MVRegister:
        encoded = _canonical_json(value)
        visible = {existing for existing, _ in self._values if existing not in self._superseded}
        values = self._value_map()
        values[dot] = encoded
        return MVRegister(values, self._superseded | visible)

    def values(self) -> tuple[object, ...]:
        result = [
            json.loads(encoded) for dot, encoded in self._values if dot not in self._superseded
        ]
        return tuple(result)

    def merge(self, other: MVRegister) -> MVRegister:
        values = self._value_map()
        for dot, encoded in other._values:
            existing = values.get(dot)
            if existing is not None and existing != encoded:
                raise ValueError("same Dot cannot identify different register values")
            values[dot] = encoded
        return MVRegister(values, self._superseded | other._superseded)

    def to_dict(self) -> dict[str, object]:
        return {
            "values": [
                {
                    "actor": dot.actor.wire_key(),
                    "counter": dot.counter,
                    "value": json.loads(encoded),
                }
                for dot, encoded in self._values
            ],
            "superseded": [
                {"actor": dot.actor.wire_key(), "counter": dot.counter}
                for dot in sorted(self._superseded)
            ],
        }
