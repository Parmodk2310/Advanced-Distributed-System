"""Repository contract for durable distributed-system state."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from distsys.persistence.models import DurableCausalState, DurableNodeIdentity, RepositoryHealth
from distsys.resilience.deadline import Deadline
from distsys.storage import StoredCrdtEntry


class StateRepository(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def integrity_check(self) -> RepositoryHealth: ...

    async def load_identity(self) -> DurableNodeIdentity | None: ...

    async def initialize_identity(self, configured_node_id: str) -> DurableNodeIdentity: ...

    async def load_clock(self) -> DurableCausalState | None: ...

    async def save_clock(
        self, state: DurableCausalState, deadline: Deadline | None = None
    ) -> None: ...

    async def load_entries(self) -> tuple[StoredCrdtEntry, ...]: ...

    async def commit_mutation(
        self,
        entry: StoredCrdtEntry,
        causal_state: DurableCausalState,
        deadline: Deadline | None = None,
    ) -> None: ...

    async def commit_observed_entry(
        self,
        entry: StoredCrdtEntry,
        causal_state: DurableCausalState,
        deadline: Deadline | None = None,
    ) -> None: ...

    async def mark_authority(self, key: str, authoritative: bool) -> None: ...

    async def backup(self, destination: Path) -> Path: ...
