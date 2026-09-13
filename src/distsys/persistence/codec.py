"""Deterministic JSON encoding for durable causal CRDT state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from distsys.causal import CausalActor, Dot, VersionVector
from distsys.crdt import CrdtType, GCounter, MVRegister, ORSet, PNCounter
from distsys.storage import StoredCrdtEntry
from distsys.storage.models import CrdtState


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    )


def _parse_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid durable JSON payload") from exc


def encode_actor(actor: CausalActor) -> dict[str, object]:
    return {"node_id": actor.node_id, "incarnation": actor.incarnation}


def decode_actor(data: object) -> CausalActor:
    if not isinstance(data, dict):
        raise TypeError("causal actor must be an object")
    node_id = data.get("node_id")
    incarnation = data.get("incarnation")
    if not isinstance(node_id, str) or not isinstance(incarnation, int):
        raise TypeError("invalid causal actor")
    return CausalActor(node_id, incarnation)


def encode_dot(dot: Dot) -> dict[str, object]:
    return {"actor": encode_actor(dot.actor), "counter": dot.counter}


def decode_dot(data: object) -> Dot:
    if not isinstance(data, dict) or not isinstance(data.get("counter"), int):
        raise TypeError("invalid causal dot")
    return Dot(decode_actor(data.get("actor")), data["counter"])


def encode_version_vector(vector: VersionVector) -> str:
    payload = [
        {"actor": encode_actor(actor), "counter": counter} for actor, counter in vector.items()
    ]
    return _canonical_json(payload)


def decode_version_vector(raw: str) -> VersionVector:
    payload = _parse_json(raw)
    if not isinstance(payload, list):
        raise TypeError("version vector payload must be a list")
    entries: dict[CausalActor, int] = {}
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("counter"), int):
            raise TypeError("invalid version vector entry")
        actor = decode_actor(item.get("actor"))
        counter = item["counter"]
        existing = entries.get(actor)
        if existing is not None and existing != counter:
            raise ValueError("duplicate actor with conflicting counter")
        entries[actor] = counter
    return VersionVector(entries)


def _encode_gcounter(counter: GCounter) -> list[dict[str, object]]:
    return [{"actor": encode_actor(actor), "value": value} for actor, value in counter.components()]


def _decode_gcounter(payload: object) -> GCounter:
    if not isinstance(payload, list):
        raise TypeError("gcounter payload must be a list")
    components: dict[CausalActor, int] = {}
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("value"), int):
            raise TypeError("invalid gcounter component")
        components[decode_actor(item.get("actor"))] = item["value"]
    return GCounter(components)


def encode_crdt_state(state: CrdtState, crdt_type: CrdtType) -> str:
    if crdt_type is CrdtType.GCOUNTER and isinstance(state, GCounter):
        payload: object = {"components": _encode_gcounter(state)}
    elif crdt_type is CrdtType.PNCOUNTER and isinstance(state, PNCounter):
        payload = {
            "positive": _encode_gcounter(state.positive),
            "negative": _encode_gcounter(state.negative),
        }
    elif crdt_type is CrdtType.ORSET and isinstance(state, ORSet):
        payload = {
            "adds": [
                {
                    "element": element,
                    "dots": [encode_dot(dot) for dot in sorted(dots)],
                }
                for element, dots in state.additions()
            ],
            "removed": [encode_dot(dot) for dot in sorted(state.removed())],
        }
    elif crdt_type is CrdtType.MVREGISTER and isinstance(state, MVRegister):
        payload = {
            "values": [
                {"dot": encode_dot(dot), "value_json": value_json}
                for dot, value_json in state.entries()
            ],
            "superseded": [encode_dot(dot) for dot in sorted(state.superseded())],
        }
    else:
        raise TypeError("CRDT state does not match CRDT type")
    return _canonical_json(payload)


def decode_crdt_state(raw: str, crdt_type: CrdtType) -> CrdtState:
    payload = _parse_json(raw)
    if not isinstance(payload, dict):
        raise TypeError("CRDT payload must be an object")

    if crdt_type is CrdtType.GCOUNTER:
        return _decode_gcounter(payload.get("components"))
    if crdt_type is CrdtType.PNCOUNTER:
        return PNCounter(
            _decode_gcounter(payload.get("positive")),
            _decode_gcounter(payload.get("negative")),
        )
    if crdt_type is CrdtType.ORSET:
        adds_raw = payload.get("adds")
        removed_raw = payload.get("removed")
        if not isinstance(adds_raw, list) or not isinstance(removed_raw, list):
            raise ValueError("invalid ORSet durable payload")
        adds: dict[str, set[Dot]] = {}
        for item in adds_raw:
            if not isinstance(item, dict) or not isinstance(item.get("element"), str):
                raise TypeError("invalid ORSet add entry")
            dots_raw = item.get("dots")
            if not isinstance(dots_raw, list):
                raise TypeError("invalid ORSet dots")
            adds[item["element"]] = {decode_dot(dot) for dot in dots_raw}
        return ORSet(adds, {decode_dot(dot) for dot in removed_raw})
    if crdt_type is CrdtType.MVREGISTER:
        values_raw = payload.get("values")
        superseded_raw = payload.get("superseded")
        if not isinstance(values_raw, list) or not isinstance(superseded_raw, list):
            raise ValueError("invalid MVRegister durable payload")
        values: dict[Dot, str] = {}
        for item in values_raw:
            if not isinstance(item, dict) or not isinstance(item.get("value_json"), str):
                raise TypeError("invalid MVRegister value entry")
            dot = decode_dot(item.get("dot"))
            _parse_json(item["value_json"])
            values[dot] = item["value_json"]
        return MVRegister(values, {decode_dot(dot) for dot in superseded_raw})
    raise ValueError(f"unsupported CRDT type: {crdt_type}")


@dataclass(frozen=True, slots=True)
class EncodedCrdtEntry:
    key: str
    crdt_type: str
    state_json: str
    state_version_json: str
    causal_context_json: str


def encode_entry(entry: StoredCrdtEntry) -> EncodedCrdtEntry:
    return EncodedCrdtEntry(
        key=entry.key,
        crdt_type=entry.crdt_type.value,
        state_json=encode_crdt_state(entry.state, entry.crdt_type),
        state_version_json=encode_version_vector(entry.state_version),
        causal_context_json=encode_version_vector(entry.causal_context),
    )


def decode_entry(encoded: EncodedCrdtEntry) -> StoredCrdtEntry:
    try:
        crdt_type = CrdtType(encoded.crdt_type)
    except ValueError as exc:
        raise ValueError(f"unknown CRDT type: {encoded.crdt_type}") from exc
    return StoredCrdtEntry(
        key=encoded.key,
        crdt_type=crdt_type,
        state=decode_crdt_state(encoded.state_json, crdt_type),
        state_version=decode_version_vector(encoded.state_version_json),
        causal_context=decode_version_vector(encoded.causal_context_json),
    )
