"""Client-carried causal session tokens."""

from __future__ import annotations

from dataclasses import dataclass

from distsys.causal.version_vector import VersionVector


@dataclass(frozen=True, slots=True)
class CausalToken:
    version: VersionVector

    @classmethod
    def empty(cls) -> CausalToken:
        return cls(VersionVector())

    def merge(self, other: CausalToken) -> CausalToken:
        return CausalToken(self.version.merge(other.version))
