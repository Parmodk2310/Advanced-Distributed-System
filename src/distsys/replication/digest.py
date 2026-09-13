"""Causal summaries used by digest-driven anti-entropy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from distsys.causal import VersionRelation, VersionVector
from distsys.crdt import CrdtType
from distsys.storage import StoredCrdtEntry


@dataclass(frozen=True, slots=True)
class CrdtDigestEntry:
    key: str
    crdt_type: CrdtType
    state_version: VersionVector
    causal_context: VersionVector

    @classmethod
    def from_entry(cls, entry: StoredCrdtEntry) -> CrdtDigestEntry:
        return cls(
            entry.key,
            entry.crdt_type,
            entry.state_version,
            entry.causal_context,
        )


class DigestRelation(str, Enum):
    EQUAL = "equal"
    LOCAL_AHEAD = "local_ahead"
    REMOTE_AHEAD = "remote_ahead"
    CONCURRENT = "concurrent"
    METADATA_ONLY = "metadata_only"


def compare_digest(local: CrdtDigestEntry, remote: CrdtDigestEntry) -> DigestRelation:
    if local.key != remote.key:
        raise ValueError("digest keys must match")
    if local.crdt_type is not remote.crdt_type:
        raise ValueError("digest CRDT types must match")

    relation = local.state_version.compare(remote.state_version)
    if relation is VersionRelation.EQUAL:
        if local.causal_context == remote.causal_context:
            return DigestRelation.EQUAL
        return DigestRelation.METADATA_ONLY
    if relation is VersionRelation.AFTER:
        return DigestRelation.LOCAL_AHEAD
    if relation is VersionRelation.BEFORE:
        return DigestRelation.REMOTE_AHEAD
    return DigestRelation.CONCURRENT
