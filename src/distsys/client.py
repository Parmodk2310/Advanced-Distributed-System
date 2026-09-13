"""Phase-1 client with both one-shot and persistent sequential connections."""

from __future__ import annotations

import asyncio
import ssl
from typing import Any, Self

from distsys.protocol.codec import decode_task_response, encode_task_request
from distsys.protocol.framing import DEFAULT_MAX_FRAME_SIZE, encode_frame, read_message
from distsys.protocol.message import Message


class CorrelationMismatch(ConnectionError):
    pass


class RemoteTaskError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DistributedClient:
    """Client supporting correctness-first one-shot requests and persistent sessions.

    `request()` keeps the original Phase-1 behavior: one TCP connection per request.
    For many sequential requests, call `connect()` once and then use
    `request_connected()` before `close()`.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        client_id: str = "client",
        timeout_seconds: float = 5.0,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
        ssl_context: ssl.SSLContext | None = None,
        server_hostname: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout_seconds = timeout_seconds
        self.max_frame_size = max_frame_size
        self.ssl_context = ssl_context
        self.server_hostname = server_hostname
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        if self.connected:
            return
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(
                self.host,
                self.port,
                ssl=self.ssl_context,
                server_hostname=self.server_hostname if self.ssl_context is not None else None,
            ),
            timeout=self.timeout_seconds,
        )

    async def close(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _round_trip(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        task_name: str,
        payload: Any,
        *,
        routing_key: str = "",
    ) -> Any:
        request_payload = encode_task_request(task_name, payload, routing_key=routing_key)
        request = Message.new_request(sender_id=self.client_id, payload=request_payload)

        writer.write(encode_frame(request, max_frame_size=self.max_frame_size))
        await asyncio.wait_for(writer.drain(), timeout=self.timeout_seconds)

        response = await asyncio.wait_for(
            read_message(reader, max_frame_size=self.max_frame_size),
            timeout=self.timeout_seconds,
        )
        if response.correlation_id != request.correlation_id:
            raise CorrelationMismatch(
                f"expected {request.correlation_id}, got {response.correlation_id}"
            )

        decoded = decode_task_response(response.payload)
        if not decoded.success:
            raise RemoteTaskError(decoded.error_code, decoded.error_message)
        return decoded.result

    async def request(self, task_name: str, payload: Any, *, routing_key: str = "") -> Any:
        """Send a one-shot request using a fresh TCP connection."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                self.host,
                self.port,
                ssl=self.ssl_context,
                server_hostname=self.server_hostname if self.ssl_context is not None else None,
            ),
            timeout=self.timeout_seconds,
        )
        try:
            return await self._round_trip(
                reader, writer, task_name, payload, routing_key=routing_key
            )
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def request_connected(
        self, task_name: str, payload: Any, *, routing_key: str = ""
    ) -> Any:
        """Send a sequential request over an already-open persistent connection."""
        if not self.connected or self._reader is None or self._writer is None:
            raise ConnectionError("client is not connected; call connect() first")

        # Phase 1 persistent mode is sequential, not multiplexed. The lock makes
        # accidental concurrent use deterministic until correlation-future
        # multiplexing is introduced in a later phase.
        async with self._request_lock:
            return await self._round_trip(
                self._reader,
                self._writer,
                task_name,
                payload,
                routing_key=routing_key,
            )
