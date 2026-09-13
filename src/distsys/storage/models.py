"""Immutable storage models for replicated CRDT state."""

from __future__ import annotations

from dataclasses import dataclass

from distsys.causal import VersionVector
from distsys.crdt import CrdtType, GCounter, MVRegister, ORSet, PNCounter

CrdtState = GCounter | PNCounter | ORSet | MVRegister

_EXPECTED_STATE = {
    CrdtType.GCOUNTER: GCounter,
    CrdtType.PNCOUNTER: PNCounter,
    CrdtType.ORSET: ORSet,
    CrdtType.MVREGISTER: MVRegister,
}


@dataclass(frozen=True, slots=True)
class StoredCrdtEntry:
    key: str
    crdt_type: CrdtType
    state: CrdtState
    state_version: VersionVector
    causal_context: VersionVector

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("key must not be empty")
        expected = _EXPECTED_STATE[self.crdt_type]
        if not isinstance(self.state, expected):
            raise TypeError(f"state for {self.crdt_type.value} must be {expected.__name__}")

    def with_context(self, causal_context: VersionVector) -> StoredCrdtEntry:
        return StoredCrdtEntry(
            self.key,
            self.crdt_type,
            self.state,
            self.state_version,
            causal_context,
        )
