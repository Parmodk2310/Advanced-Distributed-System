"""Targeted causal frontier repair before serving reads or writes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from distsys.causal import VersionVector
from distsys.cluster.member import ClusterMember
from distsys.replication.replica_selector import ReplicaSelector
from distsys.resilience.deadline import Deadline, DeadlineExceeded
from distsys.storage import CrdtStore, StoredCrdtEntry


class CausalUnavailableError(RuntimeError):
    """Required causal frontier could not be obtained before the deadline."""


@dataclass(frozen=True, slots=True)
class PeerCrdtFetch:
    peer_node_id: str
    entry: StoredCrdtEntry | None
    causal_frontier: VersionVector


@dataclass(frozen=True, slots=True)
class CausalRepairResult:
    satisfied: bool
    merged_version: VersionVector
    contacted_nodes: tuple[str, ...]
    successful_nodes: tuple[str, ...]


class CausalRepairPeer(Protocol):
    async def fetch_state(
        self,
        peer: ClusterMember,
        key: str,
        deadline: Deadline,
    ) -> PeerCrdtFetch: ...


class CausalRepairService:
    def __init__(
        self,
        local_node_id: str,
        store: CrdtStore,
        selector: ReplicaSelector,
        peer: CausalRepairPeer,
    ) -> None:
        self.local_node_id = local_node_id
        self.store = store
        self.selector = selector
        self.peer = peer

    async def ensure(
        self,
        key: str,
        required: VersionVector,
        deadline: Deadline,
    ) -> CausalRepairResult:
        local = await self.store.get(key)
        local_version = local.causal_context if local is not None else VersionVector()
        if local_version.dominates(required):
            return CausalRepairResult(True, local_version, (), ())

        peers = tuple(
            member for member in self.selector.replicas(key) if member.node_id != self.local_node_id
        )
        contacted = tuple(member.node_id for member in peers)
        if not peers:
            raise CausalUnavailableError("required causal frontier is unavailable")

        coroutines = [self.peer.fetch_state(member, key, deadline) for member in peers]
        try:
            raw_results = await deadline.run(asyncio.gather(*coroutines, return_exceptions=True))
        except DeadlineExceeded as exc:
            raise CausalUnavailableError(
                "required causal frontier was not obtained before the request deadline"
            ) from exc

        merged_version = local_version
        successful: list[str] = []
        for result in raw_results:
            if isinstance(result, BaseException):
                continue
            successful.append(result.peer_node_id)
            merged_version = merged_version.merge(result.causal_frontier)
            if result.entry is not None:
                merged = await self.store.merge_entry(result.entry)
                merged_version = merged_version.merge(merged.causal_context)

        current = await self.store.get(key)
        if current is not None:
            merged_version = merged_version.merge(current.causal_context)
            if current.causal_context != merged_version:
                current = await self.store.merge_metadata(key, merged_version)
                if current is not None:
                    merged_version = current.causal_context

        if not merged_version.dominates(required):
            raise CausalUnavailableError("required causal frontier is unavailable")

        return CausalRepairResult(
            True,
            merged_version,
            contacted,
            tuple(successful),
        )
