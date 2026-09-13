"""Asynchronous distributed node with Phase-3 cluster-aware routing."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from distsys.cluster.cluster_router import (
    LocalOverloadedError,
    PeerUnavailableError,
)
from distsys.cluster.codec import decode_forwarded_request
from distsys.cluster.consistent_hash import NoRouteError
from distsys.cluster.peer_client import PeerApplicationError
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
from distsys.proto import messages_pb2
from distsys.protocol.codec import decode_task_request, encode_task_response
from distsys.protocol.errors import DecodeError, ProtocolError
from distsys.protocol.framing import encode_frame, read_message
from distsys.protocol.message import Message, MessageType
from distsys.resilience.backpressure import BackpressureController
from distsys.resilience.deadline import Deadline, DeadlineExceeded
from distsys.resilience.rate_limiter import TokenBucketRateLimiter
from distsys.utils.config import Settings

logger = logging.getLogger("distsys.node")

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
            self._server = await asyncio.start_server(
                self._connection_entrypoint,
                self.settings.host,
                self.settings.port,
            )
            if self.settings.cluster_enabled:
                self.cluster_service = ClusterService(
                    settings=self.settings,
                    bound_port=self.bound_port,
                    execute_local=self._execute_local,
                )
                await self.cluster_service.start()
        except Exception:
            if self.cluster_service is not None:
                await self.cluster_service.stop()
                self.cluster_service = None
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()
                self._server = None
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

        if self.cluster_service is not None:
            await self.cluster_service.stop()
            self.cluster_service = None

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

            response = await self.handle_message(message)
            writer.write(encode_frame(response, max_frame_size=self.settings.max_frame_size))
            await writer.drain()

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

    async def handle_message(self, message: Message) -> Message:
        started_ns = time.perf_counter_ns()
        task_name = "unknown"
        status = "internal_error"

        if message.msg_type in _CONTROL_TYPES:
            return await self._handle_control(message)

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
