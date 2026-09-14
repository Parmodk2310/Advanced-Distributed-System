"""Phase 6 observability wrapper around the verified Phase 5 DistributedNode.

The base node keeps ownership of all correctness, routing, persistence, recovery,
coordination, and TLS semantics. This subclass adds telemetry at boundaries and
wires optional metric/tracing hooks into existing services without creating a
second execution path.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

from opentelemetry.trace import Status, StatusCode

from distsys.cluster.member import MemberStatus
from distsys.node import DistributedNode
from distsys.observability.health import ObservabilityServer
from distsys.observability.metrics import Metrics
from distsys.observability.tracing import TracingRuntime
from distsys.proto import messages_pb2
from distsys.protocol.codec import decode_task_response
from distsys.protocol.message import Message, MessageType
from distsys.replication.codec import decode_crdt_response
from distsys.utils.config import Settings

logger = logging.getLogger("distsys.observed_node")

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

_ERROR_STATUS = {
    messages_pb2.TIMEOUT: "timeout",
    messages_pb2.OVERLOADED: "overloaded",
    messages_pb2.RATE_LIMITED: "rate_limited",
    messages_pb2.NO_ROUTE: "no_route",
    messages_pb2.PEER_UNAVAILABLE: "unavailable",
    messages_pb2.CAUSAL_UNAVAILABLE: "unavailable",
    messages_pb2.COORDINATION_UNAVAILABLE: "unavailable",
    messages_pb2.PERSISTENCE_UNAVAILABLE: "unavailable",
}


class ObservedDistributedNode(DistributedNode):
    """Additive Phase 6 node; Phase 5 behavior remains in ``DistributedNode``."""

    def __init__(self, settings: Settings, **kwargs) -> None:
        super().__init__(settings, **kwargs)
        self.metrics = Metrics(
            settings.node_id,
            enabled=settings.observability_enabled and settings.metrics_enabled,
        )
        self.tracing = TracingRuntime.create(settings, settings.node_id)
        self.observability_server = (
            ObservabilityServer(
                settings.observability_host,
                settings.observability_port,
                settings.node_id,
                self.metrics,
                self.health.snapshot,
            )
            if settings.observability_enabled
            else None
        )
        self._observability_task: asyncio.Task[None] | None = None

    @property
    def bound_observability_port(self) -> int:
        if self.observability_server is None:
            return self.settings.observability_port
        return self.observability_server.bound_port

    async def start(self) -> None:
        if self.is_running:
            return
        started = time.perf_counter()
        if self.observability_server is not None:
            await self.observability_server.start()
            self._observability_task = asyncio.create_task(
                self._poll_runtime_metrics(),
                name=f"{self.settings.node_id}-phase6-observability",
            )
        try:
            with self.tracing.tracer.start_as_current_span(
                "distsys.recovery.restore",
                attributes={"distsys.node.id": self.settings.node_id},
            ) as span:
                try:
                    await super().start()
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR))
                    self.metrics.observe_recovery("failure", time.perf_counter() - started)
                    raise
                else:
                    self.metrics.observe_recovery("success", time.perf_counter() - started)
            self._wire_existing_services()
            await self._refresh_runtime_metrics()
        except BaseException:
            await self._stop_observability_runtime()
            raise

    async def stop(self) -> None:
        try:
            await super().stop()
        finally:
            await self._stop_observability_runtime()

    async def _stop_observability_runtime(self) -> None:
        task, self._observability_task = self._observability_task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if self.observability_server is not None:
            await self.observability_server.stop()
        await self.tracing.shutdown(self.settings.otel_export_timeout_seconds)

    def _wire_existing_services(self) -> None:
        if self.cluster_service is not None:
            self.cluster_service.peer_client.metrics = self.metrics
            self.cluster_service.peer_client.tracing = self.tracing
        if self.crdt_service is not None:
            self.crdt_service.peer_client.metrics = self.metrics
            self.crdt_service.peer_client.tracing = self.tracing
            self.crdt_service.replication.metrics = self.metrics
            store = self.crdt_service.store
            if hasattr(store, "metrics"):
                setattr(store, "metrics", self.metrics)  # noqa: B010

    async def _poll_runtime_metrics(self) -> None:
        while True:
            try:
                await self._refresh_runtime_metrics()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("runtime metric refresh failed", exc_info=True)
            await asyncio.sleep(0.5)

    async def _refresh_runtime_metrics(self) -> None:
        snapshot = await self.health.snapshot()
        self.metrics.set_recovery_phase(snapshot.recovery_phase)
        self.metrics.set_coordination(snapshot.coordination)
        if self.cluster_service is not None:
            members = await self.cluster_service.membership.snapshot()
            self.metrics.set_members(
                alive=sum(member.status is MemberStatus.ALIVE for member in members),
                suspect=sum(member.status is MemberStatus.SUSPECT for member in members),
                dead=sum(member.status is MemberStatus.DEAD for member in members),
            )
        if self.crdt_service is not None:
            depth = await self.crdt_service.replication.outbox.pending_count()
            self.metrics.set_replication_queue_depth(depth)

    @staticmethod
    def _category(message: Message) -> str:
        if message.msg_type in _CONTROL_TYPES:
            return "cluster"
        if message.msg_type in _CRDT_TYPES:
            return "crdt"
        return "task"

    @staticmethod
    def _task_status(response: Message) -> str:
        try:
            decoded = decode_task_response(response.payload)
        except Exception:  # noqa: BLE001
            return "error"
        if decoded.success:
            return "success"
        return _ERROR_STATUS.get(decoded.error_code, "error")

    @staticmethod
    def _crdt_status(response: Message) -> str:
        if response.msg_type is not MessageType.CRDT_RESPONSE:
            return "success"
        try:
            decoded = decode_crdt_response(response.payload)
        except Exception:  # noqa: BLE001
            return "error"
        if decoded.success:
            return "success"
        return _ERROR_STATUS.get(decoded.error_code, "error")

    async def handle_message(self, message: Message) -> Message:
        category = self._category(message)
        started = time.perf_counter()
        status = "error"
        self.metrics.request_started(category)
        carrier = {
            key: value
            for key, value in {
                "traceparent": message.traceparent,
                "tracestate": message.tracestate,
            }.items()
            if value
        }
        parent = self.tracing.extract(carrier)
        with self.tracing.tracer.start_as_current_span(
            "distsys.request",
            context=parent,
            attributes={
                "distsys.node.id": self.settings.node_id,
                "distsys.message.type": category,
                "distsys.forwarded": message.msg_type
                in {MessageType.FORWARDED_REQUEST, MessageType.CRDT_REPLICATE},
                "distsys.correlation_id": message.correlation_id,
            },
        ) as span:
            try:
                response = await super().handle_message(message)
                if category == "task":
                    status = self._task_status(response)
                elif category == "crdt":
                    status = self._crdt_status(response)
                else:
                    status = "success"
                span.set_attribute("distsys.status", status)
                if status != "success":
                    span.set_status(Status(StatusCode.ERROR))
                return response
            except BaseException as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                self.metrics.request_finished(category, status, time.perf_counter() - started)
                if status == "rate_limited":
                    self.metrics.rate_limited()
                elif status == "overloaded":
                    self.metrics.overloaded("compute")
