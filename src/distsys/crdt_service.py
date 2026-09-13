"""Causally safe CRDT read/write orchestration for Phase 4."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from distsys.causal import CausalActor, CausalClock, CausalToken, VersionVector
from distsys.cluster.consistent_hash import NoRouteError
from distsys.crdt import CrdtType, GCounter, MVRegister, ORSet, PNCounter
from distsys.persistence.errors import PersistenceBackpressureError, PersistenceUnavailableError
from distsys.proto import messages_pb2
from distsys.protocol.errors import DecodeError
from distsys.protocol.message import Message, MessageType
from distsys.replication.causal_repair import CausalUnavailableError
from distsys.replication.codec import (
    CrdtMutationData,
    CrdtReadData,
    CrdtResponseData,
    decode_digest_request,
    decode_fetch_request,
    decode_mutation_request,
    decode_read_request,
    decode_replication,
    encode_crdt_response,
    encode_digest_response,
)
from distsys.replication.outbox import ReplicationBackpressureError
from distsys.replication.peer_client import (
    AntiEntropyPeerAdapter,
    CausalRepairPeerAdapter,
    CrdtPeerClient,
    CrdtRemoteError,
    ReplicationTransportAdapter,
)
from distsys.replication.service import ReplicationService
from distsys.resilience.deadline import Deadline, DeadlineExceeded
from distsys.resilience.retry import RetryPolicy
from distsys.storage import CrdtStore, StoredCrdtEntry
from distsys.storage.protocol import CrdtStateStore
from distsys.utils.config import Settings

logger = logging.getLogger("distsys.crdt.service")


class CrdtService:
    """Coordinates causal validation, CRDT mutation, and replication."""

    def __init__(
        self,
        *,
        settings: Settings,
        cluster_service: Any,
        peer_client: Any | None = None,
        store: CrdtStateStore | None = None,
        actor: CausalActor | None = None,
        clock: CausalClock | None = None,
        commit_local: (
            Callable[[StoredCrdtEntry, VersionVector, Deadline], Awaitable[StoredCrdtEntry]] | None
        ) = None,
    ) -> None:
        if not settings.cluster_enabled:
            raise ValueError("CRDT service requires cluster mode")
        if cluster_service is None:
            raise ValueError("cluster_service is required")

        self.settings = settings
        self.cluster_service = cluster_service
        self.local_member = cluster_service.local_member
        self.local_node_id = self.local_member.node_id
        self.actor = actor or CausalActor(self.local_node_id, self.local_member.incarnation)
        self.clock = clock or CausalClock(self.actor)
        if self.clock.actor != self.actor:
            raise ValueError("clock actor must match CRDT service actor")
        self.store: CrdtStateStore = store or CrdtStore()
        self._commit_local = commit_local or self._commit_local_in_memory
        self.peer_client = peer_client or CrdtPeerClient(
            local_node_id=self.local_node_id,
            max_frame_size=settings.max_frame_size,
        )
        self._peer_cache: dict[str, Any] = {self.local_node_id: self.local_member}

        transport_timeout = min(1.0, settings.request_timeout_seconds)
        replication_peer = ReplicationTransportAdapter(
            self.peer_client,
            self._resolve_peer,
            transport_timeout,
        )
        repair_peer = CausalRepairPeerAdapter(
            self.peer_client,
            timeout_cap_seconds=transport_timeout,
        )
        anti_entropy_peer = AntiEntropyPeerAdapter(
            self.peer_client,
            self.store,
            timeout_seconds=transport_timeout,
        )
        self.replication = ReplicationService(
            local_node_id=self.local_node_id,
            store=self.store,
            ring=cluster_service.ring,
            replication_factor=settings.crdt_replication_factor,
            replication_peer=replication_peer,
            repair_peer=repair_peer,
            anti_entropy_peer=anti_entropy_peer,
            peer_provider=self._alive_peers,
            queue_capacity=settings.crdt_replication_queue_capacity,
            worker_count=settings.crdt_replication_workers,
            retry_policy=RetryPolicy(
                max_attempts=settings.crdt_replication_retry_max_attempts,
                base_delay_seconds=settings.crdt_replication_retry_base_delay_seconds,
                max_delay_seconds=settings.crdt_replication_retry_max_delay_seconds,
            ),
            anti_entropy_interval_seconds=settings.crdt_anti_entropy_interval_seconds,
            anti_entropy_batch_size=settings.crdt_anti_entropy_batch_size,
        )

    async def _alive_peers(self):
        members = await self.cluster_service.membership.alive_members(include_self=False)
        for member in members:
            self._peer_cache[member.node_id] = member
        return tuple(members)

    def _resolve_peer(self, node_id: str):
        return self._peer_cache.get(node_id)

    def _replicas(self, key: str):
        replicas = self.replication.selector.replicas(key)
        for member in replicas:
            self._peer_cache[member.node_id] = member
        return replicas

    async def start_fast_path(self) -> None:
        await self._alive_peers()
        await self.replication.start_fast_path()

    async def start_anti_entropy(self) -> None:
        await self.replication.start_anti_entropy()

    async def start(self) -> None:
        await self.start_fast_path()
        await self.start_anti_entropy()

    async def stop(self) -> None:
        await self.replication.stop()

    @staticmethod
    def _materialize(entry: StoredCrdtEntry) -> object:
        state = entry.state
        if isinstance(state, (GCounter, PNCounter)):
            return state.value()
        if isinstance(state, ORSet):
            return sorted(state.value())
        if isinstance(state, MVRegister):
            return list(state.values())
        raise TypeError("unsupported CRDT state type")

    async def _frontier(self) -> VersionVector:
        return await self.clock.frontier()

    async def _error(self, code: int, message: str) -> CrdtResponseData:
        return CrdtResponseData(
            success=False,
            error_code=code,
            error_message=message,
            served_by=self.local_node_id,
            peer_frontier=await self._frontier(),
        )

    async def _success(
        self,
        entry: StoredCrdtEntry,
        *,
        repair_performed: bool = False,
        include_state: bool = False,
    ) -> CrdtResponseData:
        await self.clock.observe(entry.causal_context)
        frontier = (await self._frontier()).merge(entry.causal_context)
        return CrdtResponseData(
            success=True,
            crdt_type=entry.crdt_type,
            value=self._materialize(entry),
            causal_token=CausalToken(frontier),
            served_by=self.local_node_id,
            repair_performed=repair_performed,
            state=entry if include_state else None,
            peer_frontier=frontier,
        )

    async def _route_mutation(
        self,
        request: CrdtMutationData,
        deadline: Deadline,
    ) -> CrdtResponseData | None:
        replicas = self._replicas(request.key)
        if not replicas:
            raise NoRouteError("no ALIVE CRDT replica is available")
        if any(member.node_id == self.local_node_id for member in replicas):
            return None
        if request.forwarded:
            return await self._error(
                messages_pb2.NO_ROUTE,
                "forwarded CRDT mutation reached a non-replica",
            )
        target = replicas[0]
        try:
            return await self.peer_client.forward_mutation(target, request, deadline=deadline)
        except CrdtRemoteError as exc:
            return await self._error(exc.code, exc.message)
        except DeadlineExceeded:
            raise
        except (ConnectionError, TimeoutError, OSError) as exc:
            return await self._error(messages_pb2.PEER_UNAVAILABLE, str(exc))

    async def _route_read(
        self,
        request: CrdtReadData,
        deadline: Deadline,
    ) -> CrdtResponseData | None:
        replicas = self._replicas(request.key)
        if not replicas:
            raise NoRouteError("no ALIVE CRDT replica is available")
        if any(member.node_id == self.local_node_id for member in replicas):
            return None
        if request.forwarded:
            return await self._error(
                messages_pb2.NO_ROUTE,
                "forwarded CRDT read reached a non-replica",
            )
        target = replicas[0]
        try:
            return await self.peer_client.forward_read(target, request, deadline=deadline)
        except CrdtRemoteError as exc:
            return await self._error(exc.code, exc.message)
        except DeadlineExceeded:
            raise
        except (ConnectionError, TimeoutError, OSError) as exc:
            return await self._error(messages_pb2.PEER_UNAVAILABLE, str(exc))

    async def _ensure_causal(
        self,
        key: str,
        token: CausalToken,
        deadline: Deadline,
        *,
        require_existing: bool,
    ) -> tuple[StoredCrdtEntry | None, bool]:
        current = await self.store.get(key)
        required = token.version
        if current is not None and current.causal_context.dominates(required):
            return current, False
        if current is None and not required and not require_existing:
            return None, False

        # In a one-node replica set there is nowhere to repair from. An empty key
        # with a satisfied local process frontier is therefore a genuine new key.
        replicas = self._replicas(key)
        remote_replicas = tuple(
            member for member in replicas if member.node_id != self.local_node_id
        )
        if current is None and not require_existing:
            frontier = await self._frontier()
            if frontier.dominates(required):
                return None, False

        if current is None and not remote_replicas:
            frontier = await self._frontier()
            if frontier.dominates(required):
                return None, False

        result = await self.replication.ensure_causal(key, required, deadline)
        repaired = await self.store.get(key)
        if repaired is not None and repaired.causal_context.dominates(required):
            return repaired, bool(result.contacted_nodes)
        if repaired is None and result.merged_version.dominates(required):
            return None, bool(result.contacted_nodes)
        raise CausalUnavailableError("required causal frontier is unavailable")

    @staticmethod
    def _empty_state(crdt_type: CrdtType):
        if crdt_type is CrdtType.GCOUNTER:
            return GCounter()
        if crdt_type is CrdtType.PNCOUNTER:
            return PNCounter()
        if crdt_type is CrdtType.ORSET:
            return ORSet()
        if crdt_type is CrdtType.MVREGISTER:
            return MVRegister()
        raise ValueError(f"unsupported CRDT type: {crdt_type}")

    def _apply_mutation(
        self,
        state: Any,
        request: CrdtMutationData,
        dot,
    ):
        if request.crdt_type is CrdtType.GCOUNTER:
            if request.operation != "increment" or request.amount < 1:
                raise ValueError("GCounter requires increment amount >= 1")
            assert isinstance(state, GCounter)
            return state.increment(self.actor, request.amount)

        if request.crdt_type is CrdtType.PNCOUNTER:
            assert isinstance(state, PNCounter)
            if request.operation == "increment" and request.amount >= 1:
                return state.increment(self.actor, request.amount)
            if request.operation == "decrement" and request.amount >= 1:
                return state.decrement(self.actor, request.amount)
            raise ValueError("PNCounter requires increment/decrement amount >= 1")

        if request.crdt_type is CrdtType.ORSET:
            assert isinstance(state, ORSet)
            if not isinstance(request.value, str):
                raise ValueError("ORSet value must be a string")
            if request.operation == "add":
                return state.add(request.value, dot)
            if request.operation == "remove":
                return state.remove(request.value)
            raise ValueError("ORSet requires add/remove")

        if request.crdt_type is CrdtType.MVREGISTER:
            assert isinstance(state, MVRegister)
            if request.operation != "write":
                raise ValueError("MVRegister requires write")
            return state.write(request.value, dot)

        raise ValueError(f"unsupported CRDT type: {request.crdt_type}")

    async def _commit_local_in_memory(
        self,
        entry: StoredCrdtEntry,
        frontier: VersionVector,
        deadline: Deadline,
    ) -> StoredCrdtEntry:
        del frontier, deadline
        return await self.store.replace(entry, expected_type=entry.crdt_type)

    async def mutate(
        self,
        request: CrdtMutationData,
        deadline: Deadline,
    ) -> CrdtResponseData:
        try:
            routed = await self._route_mutation(request, deadline)
            if routed is not None:
                return routed

            existing, repair_performed = await self._ensure_causal(
                request.key,
                request.causal_token,
                deadline,
                require_existing=(request.operation == "remove"),
            )
            if existing is not None and existing.crdt_type is not request.crdt_type:
                raise TypeError("cannot change CRDT type for existing key")

            replicas = self._replicas(request.key)
            replica_ids = tuple(member.node_id for member in replicas)
            reservation = await self.replication.reserve_write(request.key, replica_ids)
            try:
                async with self.store.key_lock(request.key):
                    existing = await self.store.get(request.key)
                    if existing is not None and existing.crdt_type is not request.crdt_type:
                        raise TypeError("cannot change CRDT type for existing key")

                    previous_version = (
                        existing.state_version if existing is not None else VersionVector()
                    )
                    previous_context = (
                        existing.causal_context if existing is not None else VersionVector()
                    )
                    observed = previous_context.merge(request.causal_token.version)
                    async with self.clock.staged_allocation(observed) as allocation:
                        dot = allocation.dot
                        frontier = allocation.frontier
                        state = (
                            existing.state
                            if existing is not None
                            else self._empty_state(request.crdt_type)
                        )
                        next_state = self._apply_mutation(state, request, dot)
                        next_entry = StoredCrdtEntry(
                            key=request.key,
                            crdt_type=request.crdt_type,
                            state=next_state,
                            state_version=previous_version.with_dot(dot),
                            causal_context=(
                                previous_context.merge(request.causal_token.version)
                                .merge(frontier)
                                .with_dot(dot)
                            ),
                        )
                        await self._commit_local(next_entry, frontier, deadline)
                        allocation.commit()
                await self.replication.publish_write(reservation, next_entry)
            except Exception:
                await self.replication.cancel_write(reservation)
                raise

            logger.info(
                "CRDT mutation applied",
                extra={
                    "event": "crdt_mutation_applied",
                    "node_id": self.local_node_id,
                    "key": request.key,
                    "crdt_type": request.crdt_type.value,
                },
            )
            return await self._success(next_entry, repair_performed=repair_performed)
        except PersistenceBackpressureError as exc:
            return await self._error(messages_pb2.PERSISTENCE_BACKPRESSURE, str(exc))
        except PersistenceUnavailableError as exc:
            return await self._error(messages_pb2.PERSISTENCE_UNAVAILABLE, str(exc))
        except ReplicationBackpressureError as exc:
            return await self._error(messages_pb2.REPLICATION_BACKPRESSURE, str(exc))
        except CausalUnavailableError as exc:
            return await self._error(messages_pb2.CAUSAL_UNAVAILABLE, str(exc))
        except NoRouteError as exc:
            return await self._error(messages_pb2.NO_ROUTE, str(exc))
        except DeadlineExceeded:
            return await self._error(messages_pb2.TIMEOUT, "request deadline exceeded")
        except (TypeError, ValueError) as exc:
            return await self._error(messages_pb2.INVALID_REQUEST, str(exc))

    async def read(
        self,
        request: CrdtReadData,
        deadline: Deadline,
    ) -> CrdtResponseData:
        try:
            routed = await self._route_read(request, deadline)
            if routed is not None:
                return routed

            current = await self.store.get(request.key)
            if current is None and not request.causal_token.version:
                return await self._error(messages_pb2.KEY_NOT_FOUND, "CRDT key not found")

            current, repair_performed = await self._ensure_causal(
                request.key,
                request.causal_token,
                deadline,
                require_existing=True,
            )
            if current is None:
                return await self._error(messages_pb2.KEY_NOT_FOUND, "CRDT key not found")

            logger.info(
                "CRDT read served",
                extra={
                    "event": (
                        "causal_read_repair_satisfied"
                        if repair_performed
                        else "causal_read_fast_path"
                    ),
                    "node_id": self.local_node_id,
                    "key": request.key,
                },
            )
            return await self._success(current, repair_performed=repair_performed)
        except CausalUnavailableError as exc:
            return await self._error(messages_pb2.CAUSAL_UNAVAILABLE, str(exc))
        except NoRouteError as exc:
            return await self._error(messages_pb2.NO_ROUTE, str(exc))
        except DeadlineExceeded:
            return await self._error(messages_pb2.TIMEOUT, "request deadline exceeded")

    def _wire_response(
        self,
        request: Message,
        response: CrdtResponseData,
    ) -> Message:
        return Message.new_response(
            sender_id=self.local_node_id,
            correlation_id=request.correlation_id,
            msg_type=MessageType.CRDT_RESPONSE,
            payload=encode_crdt_response(response),
        )

    async def _replicate_response(self, entry: StoredCrdtEntry) -> CrdtResponseData:
        merged = await self.replication.merge_replica_state(entry)
        await self.clock.observe(merged.causal_context)
        return await self._success(merged, include_state=True)

    async def _fetch_response(self, key: str) -> CrdtResponseData:
        entry = await self.store.get(key)
        frontier = await self._frontier()
        if entry is None:
            return CrdtResponseData(
                success=True,
                value=None,
                causal_token=CausalToken(frontier),
                served_by=self.local_node_id,
                peer_frontier=frontier,
            )
        return await self._success(entry, include_state=True)

    async def _handle_digest(self, message: Message) -> Message:
        requester, incoming, batch_size = decode_digest_request(message.payload)
        if not requester:
            raise DecodeError("CRDT digest requester_node_id is required")
        for remote in incoming:
            local = await self.store.get(remote.key)
            if (
                local is not None
                and local.crdt_type is remote.crdt_type
                and local.state_version == remote.state_version
            ):
                await self.replication.merge_metadata(remote.key, remote.causal_context)
        snapshot = await self.replication.digest_snapshot(requester)
        limit = max(1, batch_size) if batch_size else self.settings.crdt_anti_entropy_batch_size
        return Message.new_response(
            sender_id=self.local_node_id,
            correlation_id=message.correlation_id,
            msg_type=MessageType.CRDT_DIGEST_RESPONSE,
            payload=encode_digest_response(snapshot[:limit]),
        )

    async def handle_message(self, message: Message) -> Message:
        """Handle one Phase-4 client or peer message."""
        try:
            if message.msg_type is MessageType.CRDT_MUTATE_REQUEST:
                mutation_request = decode_mutation_request(message.payload)
                if mutation_request.forwarded:
                    if mutation_request.remaining_timeout_ms <= 0:
                        raise DeadlineExceeded("forwarded CRDT request deadline exceeded")
                    deadline = Deadline.after(mutation_request.remaining_timeout_ms / 1000.0)
                else:
                    deadline = Deadline.after(self.settings.request_timeout_seconds)
                return self._wire_response(message, await self.mutate(mutation_request, deadline))

            if message.msg_type is MessageType.CRDT_READ_REQUEST:
                read_request = decode_read_request(message.payload)
                if read_request.forwarded:
                    if read_request.remaining_timeout_ms <= 0:
                        raise DeadlineExceeded("forwarded CRDT request deadline exceeded")
                    deadline = Deadline.after(read_request.remaining_timeout_ms / 1000.0)
                else:
                    deadline = Deadline.after(self.settings.request_timeout_seconds)
                return self._wire_response(message, await self.read(read_request, deadline))

            if message.msg_type is MessageType.CRDT_REPLICATE:
                entry = decode_replication(message.payload)
                return self._wire_response(message, await self._replicate_response(entry))

            if message.msg_type is MessageType.CRDT_FETCH:
                return self._wire_response(
                    message,
                    await self._fetch_response(decode_fetch_request(message.payload)),
                )

            if message.msg_type is MessageType.CRDT_DIGEST:
                return await self._handle_digest(message)

            return self._wire_response(
                message,
                await self._error(
                    messages_pb2.INVALID_REQUEST,
                    f"unsupported CRDT message type: {message.msg_type.name}",
                ),
            )
        except DecodeError as exc:
            return self._wire_response(
                message,
                await self._error(messages_pb2.INVALID_REQUEST, str(exc)),
            )
        except DeadlineExceeded:
            return self._wire_response(
                message,
                await self._error(messages_pb2.TIMEOUT, "request deadline exceeded"),
            )
        except (TypeError, ValueError) as exc:
            return self._wire_response(
                message,
                await self._error(messages_pb2.INVALID_REQUEST, str(exc)),
            )
        except Exception:
            logger.exception("CRDT message handling failed")
            return self._wire_response(
                message,
                await self._error(messages_pb2.INTERNAL_ERROR, "internal server error"),
            )
