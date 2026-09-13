"""Restore durable node identity, causal state, and CRDT entries."""

from __future__ import annotations

from dataclasses import dataclass

from distsys.causal import CausalActor, CausalClock, VersionVector
from distsys.persistence.models import DurableCausalState, DurableNodeIdentity
from distsys.persistence.repository import StateRepository
from distsys.storage import CrdtStore


@dataclass(slots=True)
class RestoredNodeState:
    identity: DurableNodeIdentity
    causal_state: DurableCausalState
    clock: CausalClock
    memory_store: CrdtStore


class RestoreService:
    def __init__(self, repository: StateRepository, configured_node_id: str) -> None:
        self.repository = repository
        self.configured_node_id = configured_node_id

    async def restore(self) -> RestoredNodeState:
        await self.repository.integrity_check()
        identity = await self.repository.load_identity()
        if identity is None:
            identity = await self.repository.initialize_identity(self.configured_node_id)
        elif identity.configured_node_id != self.configured_node_id:
            # Repository implementation normally rejects this at initialization,
            # but keep restore defensive for custom repository implementations.
            await self.repository.initialize_identity(self.configured_node_id)

        actor = CausalActor(identity.configured_node_id, identity.causal_incarnation)
        causal_state = await self.repository.load_clock()
        if causal_state is None:
            causal_state = DurableCausalState(actor, 0, VersionVector())
            await self.repository.save_clock(causal_state)

        entries = await self.repository.load_entries()
        merged_frontier = causal_state.frontier
        for entry in entries:
            merged_frontier = merged_frontier.merge(entry.causal_context)
        if merged_frontier != causal_state.frontier:
            causal_state = DurableCausalState(
                actor=actor,
                local_counter=merged_frontier.get(actor),
                frontier=merged_frontier,
            )
            await self.repository.save_clock(causal_state)

        memory = CrdtStore()
        for entry in entries:
            await memory.replace(entry, expected_type=entry.crdt_type)
        clock = CausalClock(actor)
        await clock.restore(causal_state.frontier)
        return RestoredNodeState(identity, causal_state, clock, memory)
