"""Immutable durable-state models."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from distsys.causal import CausalActor, VersionVector


@dataclass(frozen=True, slots=True)
class DurableNodeIdentity:
    node_uuid: UUID
    configured_node_id: str
    causal_incarnation: int

    def __post_init__(self) -> None:
        if not self.configured_node_id:
            raise ValueError("configured_node_id must not be empty")
        if self.causal_incarnation < 1:
            raise ValueError("causal_incarnation must be positive")


@dataclass(frozen=True, slots=True)
class DurableCausalState:
    actor: CausalActor
    local_counter: int
    frontier: VersionVector

    def __post_init__(self) -> None:
        if self.local_counter < 0:
            raise ValueError("local_counter must be non-negative")
        if self.frontier.get(self.actor) != self.local_counter:
            raise ValueError("frontier local actor component must equal local_counter")


@dataclass(frozen=True, slots=True)
class RepositoryHealth:
    healthy: bool
    schema_version: int
    message: str = ""
