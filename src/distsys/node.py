"""Asynchronous distributed node with Phase-3 cluster-aware routing."""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from typing import Any

from distsys import __version__
from distsys.cluster.cluster_router import (
    LocalOverloadedError,
    PeerUnavailableError,
)
from distsys.cluster.codec import decode_forwarded_request
from distsys.cluster.consistent_hash import NoRouteError
from distsys.cluster.member import fresh_incarnation
from distsys.cluster.peer_client import PeerApplicationError, PeerClient
from distsys.cluster.service import ClusterService
from distsys.compute.classification import TaskClassifier
from distsys.compute.errors import (
    TaskValidationError,
    WorkerPoolBrokenError,
    WorkerPoolClosedError,
    WorkerPoolSaturatedError,
)
from distsys.compute.executor import TaskExecutor
from distsys.compute.router import TaskRouter, UnknownTaskError
from distsys.compute.tasks import (
    aggregate_task,
    echo_task,
    hash_task,
    make_whoami_task,
    sort_task,
)
from distsys.compute.worker_pool import WorkerPool
from distsys.coordination.discovery import DiscoveryService
from distsys.coordination.etcd_client import EtcdGatewayCoordinationClient
from distsys.coordination.lease import LeaseManager
from distsys.coordination.models import CoordinationMember
from distsys.coordination.service import CoordinationService
from distsys.crdt_service import CrdtService
from distsys.health import HealthState, RecoveryPhase
from distsys.persistence.durable_store import DurableCrdtStore
from distsys.persistence.executor import PersistenceExecutor
from distsys.persistence.sqlite_repository import SQLiteStateRepository
from distsys.proto import messages_pb2
from distsys.protocol.codec import decode_task_request, encode_task_response
from distsys.protocol.errors import DecodeError, ProtocolError
from distsys.protocol.framing import encode_frame, read_message
from distsys.protocol.message import Message, MessageType
from distsys.recovery import RecoveryCoordinator, RecoveryReconciler, RestoreService
from distsys.replication.codec import CrdtResponseData, encode_crdt_response
from distsys.replication.peer_client import CrdtPeerClient
from distsys.resilience.backpressure import BackpressureController
from distsys.resilience.deadline import Deadline, DeadlineExceeded
from distsys.resilience.rate_limiter import TokenBucketRateLimiter
from distsys.resilience.retry import RetryPolicy
from distsys.security.errors import TlsPeerIdentityError
from distsys.security.identity import verify_node_identity
from distsys.security.tls_context import build_client_context, build_server_context
from distsys.utils.config import Settings

logger = logging.getLogger("distsys.node")

_CRDT_TYPES = {
    MessageType.CRDT_MUTATE_REQUEST,
    MessageType.CRDT_READ_REQUEST,
    MessageType.CRDT_REPLICATE,
    MessageType.CRDT_FETCH,
    MessageType.CRDT_DIGEST,
}

_CONTROL_TYPES = {
    MessageType.JOIN_REQUEST,
    MessageType.PING,
    MessageType.PING_REQ,
    MessageType.GOSSIP,
}


class DistributedNode:
    def __init__(
        self,
        settings: Settings,
        *,
        router: TaskRouter | None = None,
        classifier: TaskClassifier | None = None,
    ) -> None:
        self.settings = settings
        self.router = router or self._default_router(settings.node_id)
        self.classifier = classifier or TaskClassifier.default()
        self.worker_pool = WorkerPool(
            max_workers=settings.cpu_workers,
            max_pending=settings.cpu_queue_capacity,
        )
        self.executor = TaskExecutor(
            router=self.router,
            classifier=self.classifier,
            worker_pool=self.worker_pool,
        )
        self.backpressure = BackpressureController(capacity=settings.cpu_queue_capacity)
        self.rate_limiter = TokenBucketRateLimiter(
            rate_per_second=settings.rate_limit_rps,
            burst=settings.rate_limit_burst,
        )
        self.cluster_service: ClusterService | None = None
        self.crdt_service: CrdtService | None = None
        self.health = HealthState()
        self.persistence_executor: PersistenceExecutor | None = None
        self.repository: SQLiteStateRepository | None = None
        self.coordination_service: CoordinationService | None = None
        self.recovery_coordinator: RecoveryCoordinator | None = None
        self._server_ssl_context: ssl.SSLContext | None = None
        self._client_ssl_context: ssl.SSLContext | None = None
        self._server: asyncio.Server | None = None
        self._connections: set[asyncio.StreamWriter] = set()
        self._handler_tasks: set[asyncio.Task[None]] = set()
        self._stopping = False

    @staticmethod
    def _default_router(node_id: str) -> TaskRouter:
        router = TaskRouter()
        router.register("echo", echo_task)
        router.register("hash", hash_task)
        router.register("sort", sort_task)
        router.register("aggregate", aggregate_task)
        router.register("cluster.whoami", make_whoami_task(node_id))
        return router

    @property
    def bound_port(self) -> int:
        if not self._server or not self._server.sockets:
            return self.settings.port
        return int(self._server.sockets[0].getsockname()[1])

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._server.is_serving() and not self._stopping

    async def start(self) -> None:
        if self.is_running:
            return
        self._stopping = False
        await self.executor.start()
        try:
            self._server_ssl_context = build_server_context(self.settings)
            self._client_ssl_context = build_client_context(self.settings)

            restored = None
            if self.settings.crdt_enabled and self.settings.persistence_enabled:
                self.persistence_executor = PersistenceExecutor(
                    self.settings.persistence_queue_capacity
                )
                self.repository = SQLiteStateRepository(
                    self.settings.persistence_db_path,
                    self.persistence_executor,
                    busy_timeout_seconds=self.settings.persistence_busy_timeout_seconds,
                    synchronous=self.settings.persistence_sqlite_synchronous,
                )
                await self.repository.open()
                self.recovery_coordinator = RecoveryCoordinator(
                    health=self.health,
                    restore_service=RestoreService(self.repository, self.settings.node_id),
                )
                restored = await self.recovery_coordinator.prepare_persistence()
            else:
                await self.health.set_recovery_phase(RecoveryPhase.RESTORING)

            if self.recovery_coordinator is not None:
                await self.recovery_coordinator.mark_binding()
            else:
                await self.health.set_recovery_phase(RecoveryPhase.BINDING)
            self._server = await asyncio.start_server(
                self._connection_entrypoint,
                self.settings.host,
                self.settings.port,
                ssl=self._server_ssl_context,
            )

            if self.settings.cluster_enabled:
                membership_incarnation = fresh_incarnation()
                bootstrap_seeds = self.settings.cluster_seeds

                if self.settings.etcd_enabled:
                    if restored is None:
                        raise RuntimeError(
                            "ETCD_ENABLED clustered CRDT startup requires durable node identity"
                        )
                    if self.recovery_coordinator is not None:
                        await self.recovery_coordinator.mark_coordinating()
                    else:
                        await self.health.set_recovery_phase(RecoveryPhase.COORDINATING)
                    etcd_client = EtcdGatewayCoordinationClient(
                        self.settings.etcd_endpoints,
                        namespace=self.settings.etcd_namespace,
                        timeout_seconds=min(3.0, self.settings.request_timeout_seconds),
                    )

                    async def on_coordination_health(health) -> None:
                        await self.health.set_coordination(health.healthy, health.message)
                        metrics = getattr(self, "metrics", None)
                        if metrics is not None:
                            metrics.set_coordination(health.healthy)
                            if not health.healthy:
                                metrics.coordination_failure("lease")

                    lease = LeaseManager(
                        etcd_client,
                        ttl_seconds=self.settings.etcd_lease_ttl_seconds,
                        renew_interval_seconds=self.settings.etcd_renew_interval_seconds,
                        on_health_change=on_coordination_health,
                    )
                    discovery = DiscoveryService(etcd_client)
                    self.coordination_service = CoordinationService(etcd_client, discovery, lease)
                    coordination_member = CoordinationMember(
                        node_id=self.settings.node_id,
                        node_uuid=str(restored.identity.node_uuid),
                        host=self.settings.advertise_host or self.settings.host,
                        port=self.bound_port,
                        membership_incarnation=membership_incarnation,
                        protocol_version=5,
                        release=__version__,
                        tls_required=self.settings.tls_enabled,
                    )
                    bootstrap_seeds = await self.coordination_service.bootstrap(coordination_member)
                    await self.health.set_coordination(True, "healthy")
                else:
                    await self.health.set_coordination(True, "disabled")

                if self.recovery_coordinator is not None:
                    await self.recovery_coordinator.mark_joining_cluster()
                else:
                    await self.health.set_recovery_phase(RecoveryPhase.JOINING_CLUSTER)

                cluster_peer = PeerClient(
                    local_node_id=self.settings.node_id,
                    retry_policy=RetryPolicy(
                        max_attempts=self.settings.retry_max_attempts,
                        base_delay_seconds=self.settings.retry_base_delay_seconds,
                        max_delay_seconds=self.settings.retry_max_delay_seconds,
                    ),
                    circuit_breaker_failure_threshold=(
                        self.settings.circuit_breaker_failure_threshold
                    ),
                    circuit_breaker_recovery_seconds=(
                        self.settings.circuit_breaker_recovery_seconds
                    ),
                    max_frame_size=self.settings.max_frame_size,
                    ssl_context=self._client_ssl_context,
                )
                cluster_peer.metrics = getattr(self, "metrics", None)
                cluster_peer.tracing = getattr(self, "tracing", None)
                self.cluster_service = ClusterService(
                    settings=self.settings,
                    bound_port=self.bound_port,
                    execute_local=self._execute_local,
                    peer_client=cluster_peer,
                    incarnation=membership_incarnation,
                    bootstrap_seeds=bootstrap_seeds,
                )
                await self.cluster_service.start()
                await self.health.set_cluster(True)

                if self.settings.crdt_enabled:
                    crdt_peer = CrdtPeerClient(
                        local_node_id=self.settings.node_id,
                        max_frame_size=self.settings.max_frame_size,
                        ssl_context=self._client_ssl_context,
                    )
                    crdt_peer.metrics = getattr(self, "metrics", None)
                    crdt_peer.tracing = getattr(self, "tracing", None)
                    if restored is not None and self.repository is not None:
                        durable_store = DurableCrdtStore(
                            restored.memory_store,
                            self.repository,
                            restored.clock,
                        )
                        durable_store.metrics = getattr(self, "metrics", None)
                        self.crdt_service = CrdtService(
                            settings=self.settings,
                            cluster_service=self.cluster_service,
                            peer_client=crdt_peer,
                            store=durable_store,
                            actor=restored.causal_state.actor,
                            clock=restored.clock,
                            commit_local=durable_store.commit_local,
                        )
                        await self.crdt_service.start_fast_path()
                        reconciler = RecoveryReconciler(
                            self.settings.node_id,
                            durable_store,
                            self.crdt_service.replication,
                            self.repository,
                        )
                        assert self.recovery_coordinator is not None
                        self.recovery_coordinator.reconciler = reconciler
                        peers = await self.cluster_service.membership.alive_members(
                            include_self=False
                        )
                        await self.recovery_coordinator.reconcile(tuple(peers))
                        await self.crdt_service.start_anti_entropy()
                    else:
                        self.crdt_service = CrdtService(
                            settings=self.settings,
                            cluster_service=self.cluster_service,
                            peer_client=crdt_peer,
                        )
                        await self.crdt_service.start()
                        await self.health.set_readiness(True)
                        await self.health.set_recovery_phase(RecoveryPhase.READY)
            else:
                await self.health.set_readiness(True)
                await self.health.set_recovery_phase(RecoveryPhase.READY)
        except Exception as exc:
            if self.recovery_coordinator is not None:
                await self.recovery_coordinator.fail(exc)
            if self.crdt_service is not None:
                await self.crdt_service.stop()
                self.crdt_service = None
            if self.cluster_service is not None:
                await self.cluster_service.stop()
                self.cluster_service = None
            if self.coordination_service is not None:
                await self.coordination_service.stop()
                self.coordination_service = None
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()
                self._server = None
            if self.repository is not None:
                await self.repository.close()
                self.repository = None
            await self.executor.close()
            raise

        logger.info(
            "node ready",
            extra={
                "event": "node_ready",
                "node_id": self.settings.node_id,
                "port": self.bound_port,
                "cpu_workers": self.settings.cpu_workers,
                "cluster_enabled": self.settings.cluster_enabled,
            },
        )

    async def serve_forever(self) -> None:
        if not self.is_running:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True

        if self.crdt_service is not None:
            await self.crdt_service.stop()
            self.crdt_service = None

        if self.cluster_service is not None:
            await self.cluster_service.stop()
            self.cluster_service = None

        if self.coordination_service is not None:
            await self.coordination_service.stop()
            self.coordination_service = None

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        writers = list(self._connections)
        for writer in writers:
            writer.close()
        if writers:
            await asyncio.gather(
                *(writer.wait_closed() for writer in writers),
                return_exceptions=True,
            )

        current_task = asyncio.current_task()
        tasks = [
            task for task in self._handler_tasks if task is not current_task and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self.repository is not None:
            await self.repository.close()
            self.repository = None

        await self.executor.close()

        logger.info(
            "node stopped",
            extra={"event": "node_stopped", "node_id": self.settings.node_id},
        )

    async def _connection_entrypoint(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._handler_tasks.add(task)
        self._connections.add(writer)
        try:
            await self.handle_connection(reader, writer)
        finally:
            self._connections.discard(writer)
            if task is not None:
                self._handler_tasks.discard(task)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, asyncio.CancelledError):
                pass

    async def handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        while not self._stopping:
            try:
                message = await read_message(
                    reader,
                    max_frame_size=self.settings.max_frame_size,
                )
            except asyncio.IncompleteReadError:
                return
            except ProtocolError:
                logger.warning(
                    "protocol error",
                    extra={"event": "protocol_error", "node_id": self.settings.node_id},
                )
                return

            try:
                self._verify_authenticated_sender(message, writer)
            except TlsPeerIdentityError as exc:
                logger.warning(
                    "TLS peer identity rejected",
                    extra={
                        "event": "tls_peer_identity_mismatch",
                        "node_id": self.settings.node_id,
                        "sender_id": message.sender_id,
                        "error": str(exc),
                    },
                )
                return

            response = await self.handle_message(message)
            writer.write(encode_frame(response, max_frame_size=self.settings.max_frame_size))
            await writer.drain()

    def _verify_authenticated_sender(
        self,
        message: Message,
        writer: asyncio.StreamWriter,
    ) -> None:
        if not self.settings.tls_enabled:
            return
        ssl_object = writer.get_extra_info("ssl_object")
        if ssl_object is None:
            raise TlsPeerIdentityError("TLS connection did not expose an SSL object")
        cert = ssl_object.getpeercert()
        if not cert:
            if self.settings.mtls_required:
                raise TlsPeerIdentityError("mTLS peer did not present a certificate")
            return
        verify_node_identity(cert, message.sender_id)

    def _response(
        self,
        request: Message,
        *,
        success: bool,
        result: object | None = None,
        error_code: messages_pb2.ErrorCode = messages_pb2.ERROR_CODE_UNSPECIFIED,
        error_message: str = "",
        processing_time_us: int = 0,
    ) -> Message:
        payload = encode_task_response(
            success=success,
            result=result,
            error_code=error_code,
            error_message=error_message,
            processing_time_us=processing_time_us,
        )
        return Message.new_response(
            sender_id=self.settings.node_id,
            correlation_id=request.correlation_id,
            payload=payload,
            msg_type=MessageType.RESPONSE if success else MessageType.ERROR,
        )

    async def _execute_local(
        self,
        task_name: str,
        payload: Any,
        deadline: Deadline,
    ) -> Any:
        acquired = await self.backpressure.try_acquire()
        if not acquired:
            raise LocalOverloadedError("node is at execution capacity")
        try:
            return await self.executor.execute(task_name, payload, deadline=deadline)
        except WorkerPoolSaturatedError as exc:
            raise LocalOverloadedError("worker pool pending capacity is full") from exc
        finally:
            await self.backpressure.release()

    async def _handle_control(self, message: Message) -> Message:
        if self.cluster_service is None:
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.INVALID_REQUEST,
                error_message="cluster mode is disabled",
            )
        try:
            return await self.cluster_service.handle_control(message)
        except DecodeError as exc:
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.INVALID_REQUEST,
                error_message=str(exc),
            )

    async def _handle_crdt(self, message: Message) -> Message:
        if (
            self.settings.crdt_enabled
            and self.settings.persistence_enabled
            and message.msg_type in {MessageType.CRDT_MUTATE_REQUEST, MessageType.CRDT_READ_REQUEST}
        ):
            health = await self.health.snapshot()
            if not health.readiness:
                payload = encode_crdt_response(
                    CrdtResponseData(
                        success=False,
                        error_code=messages_pb2.RECOVERY_IN_PROGRESS,
                        error_message="durable recovery is still in progress",
                        served_by=self.settings.node_id,
                    )
                )
                return Message.new_response(
                    sender_id=self.settings.node_id,
                    correlation_id=message.correlation_id,
                    msg_type=MessageType.CRDT_RESPONSE,
                    payload=payload,
                )
        if self.crdt_service is not None:
            return await self.crdt_service.handle_message(message)
        payload = encode_crdt_response(
            CrdtResponseData(
                success=False,
                error_code=messages_pb2.INVALID_REQUEST,
                error_message="CRDT mode is disabled",
                served_by=self.settings.node_id,
            )
        )
        return Message.new_response(
            sender_id=self.settings.node_id,
            correlation_id=message.correlation_id,
            msg_type=MessageType.CRDT_RESPONSE,
            payload=payload,
        )

    async def handle_message(self, message: Message) -> Message:
        started_ns = time.perf_counter_ns()
        task_name = "unknown"
        status = "internal_error"

        if message.msg_type in _CONTROL_TYPES:
            return await self._handle_control(message)

        if message.msg_type in _CRDT_TYPES:
            return await self._handle_crdt(message)

        if message.msg_type not in (MessageType.REQUEST, MessageType.FORWARDED_REQUEST):
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.INVALID_REQUEST,
                error_message=f"unsupported message type: {message.msg_type.name}",
            )

        try:
            if message.msg_type is MessageType.FORWARDED_REQUEST:
                if self.cluster_service is None:
                    return self._response(
                        message,
                        success=False,
                        error_code=messages_pb2.INVALID_REQUEST,
                        error_message="cluster mode is disabled",
                    )
                forwarded = decode_forwarded_request(message.payload)
                task_name = forwarded.task.task_name
                if forwarded.remaining_timeout_ms <= 0:
                    raise DeadlineExceeded("forwarded request deadline exceeded")
                deadline = Deadline.after(forwarded.remaining_timeout_ms / 1000.0)
                result = await self._execute_local(
                    task_name,
                    forwarded.task.payload,
                    deadline,
                )
            else:
                request = decode_task_request(message.payload)
                task_name = request.task_name
                if not self.rate_limiter.allow():
                    status = "rate_limited"
                    return self._response(
                        message,
                        success=False,
                        error_code=messages_pb2.RATE_LIMITED,
                        error_message="request rate limit exceeded",
                        processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
                    )

                deadline = Deadline.after(self.settings.request_timeout_seconds)
                if self.cluster_service is not None and request.routing_key:
                    result = await self.cluster_service.router.execute(
                        task_name,
                        request.payload,
                        routing_key=request.routing_key,
                        deadline=deadline,
                    )
                else:
                    result = await self._execute_local(task_name, request.payload, deadline)

            status = "success"
            return self._response(
                message,
                success=True,
                result=result,
                processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
            )
        except UnknownTaskError:
            status = "unknown_task"
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.UNKNOWN_TASK,
                error_message=f"unknown task: {task_name}",
                processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
            )
        except (DecodeError, TaskValidationError) as exc:
            status = "invalid_request"
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.INVALID_REQUEST,
                error_message=str(exc),
                processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
            )
        except DeadlineExceeded:
            status = "timeout"
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.TIMEOUT,
                error_message="request deadline exceeded",
                processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
            )
        except LocalOverloadedError as exc:
            status = "overloaded"
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.OVERLOADED,
                error_message=str(exc),
                processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
            )
        except NoRouteError as exc:
            status = "no_route"
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.NO_ROUTE,
                error_message=str(exc),
                processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
            )
        except PeerUnavailableError as exc:
            status = "peer_unavailable"
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.PEER_UNAVAILABLE,
                error_message=str(exc),
                processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
            )
        except PeerApplicationError as exc:
            status = "peer_application_error"
            return self._response(
                message,
                success=False,
                error_code=exc.code,
                error_message=exc.message,
                processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
            )
        except (WorkerPoolBrokenError, WorkerPoolClosedError):
            status = "worker_pool_error"
            logger.exception("worker pool execution failed")
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.INTERNAL_ERROR,
                error_message="internal server error",
                processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
            )
        except Exception:
            status = "internal_error"
            logger.exception("task execution failed")
            return self._response(
                message,
                success=False,
                error_code=messages_pb2.INTERNAL_ERROR,
                error_message="internal server error",
                processing_time_us=(time.perf_counter_ns() - started_ns) // 1_000,
            )
        finally:
            logger.info(
                "request completed",
                extra={
                    "event": "request_completed",
                    "node_id": self.settings.node_id,
                    "correlation_id": message.correlation_id,
                    "task": task_name,
                    "status": status,
                    "duration_us": (time.perf_counter_ns() - started_ns) // 1_000,
                },
            )
