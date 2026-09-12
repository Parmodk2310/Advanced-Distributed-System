"""Built-in application tasks for Phase 2."""

from __future__ import annotations

import hashlib
from typing import Any

from distsys.compute.errors import TaskValidationError

_MAX_HASH_ROUNDS = 1_000_000
_MAX_NUMERIC_VALUES = 100_000


async def echo_task(payload: Any) -> Any:
    return payload


def _require_mapping(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TaskValidationError("payload must be a JSON object")
    return payload


def _require_numeric_values(payload: Any, *, allow_empty: bool) -> list[float | int]:
    data = _require_mapping(payload)
    values = data.get("values")
    if not isinstance(values, list):
        raise TaskValidationError("values must be a list of numbers")
    if not allow_empty and not values:
        raise TaskValidationError("values must be a non-empty list of numbers")
    if len(values) > _MAX_NUMERIC_VALUES:
        raise TaskValidationError(f"values cannot exceed {_MAX_NUMERIC_VALUES} items")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise TaskValidationError("values must be a list of numbers")
    return values


def hash_task(payload: Any) -> dict[str, Any]:
    data = _require_mapping(payload)
    raw = data.get("data")
    rounds = data.get("rounds", 50_000)

    if not isinstance(raw, str):
        raise TaskValidationError("data must be a string")
    if (
        isinstance(rounds, bool)
        or not isinstance(rounds, int)
        or not 1 <= rounds <= _MAX_HASH_ROUNDS
    ):
        raise TaskValidationError(f"rounds must be an integer between 1 and {_MAX_HASH_ROUNDS}")

    digest = raw.encode("utf-8")
    for _ in range(rounds):
        digest = hashlib.sha256(digest).digest()

    return {
        "algorithm": "sha256",
        "digest": digest.hex(),
        "rounds": rounds,
    }


def sort_task(payload: Any) -> dict[str, Any]:
    values = _require_numeric_values(payload, allow_empty=True)
    return {
        "values": sorted(values),
        "count": len(values),
    }


def aggregate_task(payload: Any) -> dict[str, Any]:
    values = _require_numeric_values(payload, allow_empty=False)
    numeric = [float(value) for value in values]
    total = float(sum(numeric))
    return {
        "count": len(numeric),
        "sum": total,
        "min": min(numeric),
        "max": max(numeric),
        "mean": total / len(numeric),
    }
