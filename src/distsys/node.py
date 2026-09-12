"""Phase-1 asynchronous distributed node."""

from __future__ import annotations

import asyncio
import logging
import time

from distsys.compute.router import TaskRouter, UnknownTaskError
from distsys.compute.tasks import echo_task
from distsys.proto import messages_pb2
from distsys.protocol.codec import (
    decode_task_request,
    encode_task_response,
)
from distsys.protocol.errors import DecodeError, ProtocolError
from distsys.protocol.framing import encode_frame, read_message
from distsys.protocol.message import Message, MessageType
from distsys.utils.config import Settings

logger = logging.getLogger("distsys.node")


class DistributedNode:
    def __init__(
        self,
        settings: Settings,
        *,
        router: TaskRouter | None = None,
    ) -> None:
        self.settings = settings
        self.router = router or self._default_router()

        # asyncio.start_server() returns asyncio.Server.
        self._server: asyncio.Server | None = None

        # Store the actual bound port once startup succeeds.
        self._bound_port: int | None = None

        self._connections: set[asyncio.StreamWriter] = set()
        self._handler_tasks: set[asyncio.Task[None]] = set()

        self._stopping = False

    @staticmethod
    def _default_router() -> TaskRouter:
        router = TaskRouter()
        router.register("echo", echo_task)
        return router

    @property
    def bound_port(self) -> int:
        if self._bound_port is not None:
            return self._bound_port

        return self.settings.port

    @property
    def is_running(self) -> bool:
        return (
            self._server is not None
            and self._server.is_serving()
            and not self._stopping
        )

    async def start(self) -> None:
        if self.is_running:
            return

        self._stopping = False

        server = await asyncio.start_server(
            self._connection_entrypoint,
            host=self.settings.host,
            port=self.settings.port,
            backlog=256,
            start_serving=False,
        )

        sockets = server.sockets

        if not sockets:
            server.close()
            await server.wait_closed()

            raise RuntimeError(
                "TCP server started without any bound sockets"
            )

        self._bound_port = int(
            sockets[0].getsockname()[1]
        )

        self._server = server

        # Explicitly begin accepting connections.
        await server.start_serving()

        # Give the event loop one cycle so the listener is fully registered.
        await asyncio.sleep(0)

        logger.info(
            "node ready",
            extra={
                "event": "node_ready",
                "node_id": self.settings.node_id,
                "host": self.settings.host,
                "port": self._bound_port,
            },
        )

    async def serve_forever(self) -> None:
        if not self.is_running:
            await self.start()

        server = self._server

        if server is None:
            raise RuntimeError("server failed to start")

        await server.serve_forever()

    async def stop(self) -> None:
        if self._stopping:
            return

        self._stopping = True

        server = self._server
        self._server = None

        # Stop accepting new connections first.
        if server is not None:
            server.close()
            await server.wait_closed()

        # Close active client connections.
        writers = list(self._connections)

        for writer in writers:
            writer.close()

        if writers:
            await asyncio.gather(
                *(
                    writer.wait_closed()
                    for writer in writers
                ),
                return_exceptions=True,
            )

        self._connections.clear()

        # Cancel connection handler tasks.
        current_task = asyncio.current_task()

        tasks = [
            task
            for task in self._handler_tasks
            if task is not current_task
            and not task.done()
        ]

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        self._handler_tasks.clear()

        # Let socket-close events propagate.
        await asyncio.sleep(0)

        logger.info(
            "node stopped",
            extra={
                "event": "node_stopped",
                "node_id": self.settings.node_id,
            },
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
            except ProtocolError as exc:
                logger.warning(
                    "protocol error",
                    extra={"event": "protocol_error", "node_id": self.settings.node_id},
                )
                return

            response = await self.handle_message(message)
            writer.write(encode_frame(response, max_frame_size=self.settings.max_frame_size))
            await writer.drain()

    async def handle_message(self, message: Message) -> Message:
        if message.msg_type is not MessageType.REQUEST:
            payload = encode_task_response(
                success=False,
                error_code=messages_pb2.INVALID_REQUEST,
                error_message=f"expected REQUEST, got {message.msg_type.name}",
            )
            return Message.new_response(
                sender_id=self.settings.node_id,
                correlation_id=message.correlation_id,
                payload=payload,
                msg_type=MessageType.ERROR,
            )

        started_ns = time.perf_counter_ns()
        task_name = "unknown"
        try:
            task_name, task_payload = decode_task_request(message.payload)
            result = await self.router.dispatch(task_name, task_payload)
            duration_us = (time.perf_counter_ns() - started_ns) // 1_000
            payload = encode_task_response(
                success=True,
                result=result,
                processing_time_us=duration_us,
            )
            status = "success"
            response_type = MessageType.RESPONSE
        except UnknownTaskError:
            duration_us = (time.perf_counter_ns() - started_ns) // 1_000
            payload = encode_task_response(
                success=False,
                error_code=messages_pb2.UNKNOWN_TASK,
                error_message=f"unknown task: {task_name}",
                processing_time_us=duration_us,
            )
            status = "unknown_task"
            response_type = MessageType.ERROR
        except DecodeError as exc:
            duration_us = (time.perf_counter_ns() - started_ns) // 1_000
            payload = encode_task_response(
                success=False,
                error_code=messages_pb2.INVALID_REQUEST,
                error_message=str(exc),
                processing_time_us=duration_us,
            )
            status = "invalid_request"
            response_type = MessageType.ERROR
        except Exception:
            duration_us = (time.perf_counter_ns() - started_ns) // 1_000
            logger.exception("task execution failed")
            payload = encode_task_response(
                success=False,
                error_code=messages_pb2.INTERNAL_ERROR,
                error_message="internal server error",
                processing_time_us=duration_us,
            )
            status = "internal_error"
            response_type = MessageType.ERROR

        logger.info(
            "request completed",
            extra={
                "event": "request_completed",
                "node_id": self.settings.node_id,
                "correlation_id": message.correlation_id,
                "task": task_name,
                "status": status,
                "duration_us": duration_us,
            },
        )

        return Message.new_response(
            sender_id=self.settings.node_id,
            correlation_id=message.correlation_id,
            payload=payload,
            msg_type=response_type,
        )
