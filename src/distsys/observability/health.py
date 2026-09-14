"""Tiny asyncio HTTP server for metrics and stable health snapshots."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Awaitable, Callable
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST

from distsys.observability.metrics import Metrics

SnapshotProvider = Callable[[], Awaitable[Any]]
_MAX_HEADER_BYTES = 16 * 1024


class ObservabilityServer:
    def __init__(
        self,
        host: str,
        port: int,
        node_id: str,
        metrics: Metrics,
        snapshot_provider: SnapshotProvider,
    ) -> None:
        self.host = host
        self.port = port
        self.node_id = node_id
        self.metrics = metrics
        self.snapshot_provider = snapshot_provider
        self._server: asyncio.Server | None = None
        self._bound_port = port

    @property
    def bound_port(self) -> int:
        return self._bound_port

    async def start(self) -> None:
        if self._server is not None:
            return

        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        listener = socket.socket(family, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.setblocking(False)
        try:
            listener.bind((self.host, self.port))
            listener.listen(socket.SOMAXCONN)
            self._server = await asyncio.start_server(
                self._handle,
                sock=listener,
                start_serving=True,
            )
            await self._server.start_serving()
        except asyncio.CancelledError:
            listener.close()
            self._server = None
            raise
        except (OSError, RuntimeError, ValueError):
            listener.close()
            self._server = None
            raise

        sockets = self._server.sockets
        if not sockets:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            raise RuntimeError("observability listener did not bind a socket")
        self._bound_port = int(sockets[0].getsockname()[1])

    async def stop(self) -> None:
        server, self._server = self._server, None
        if server is None:
            return
        server.close()
        await server.wait_closed()

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2.0)
            if len(request) > _MAX_HEADER_BYTES:
                await self._send(
                    writer,
                    431,
                    "application/json",
                    b'{"error":"headers_too_large"}',
                )
                return
            first = request.split(b"\r\n", 1)[0]
            try:
                method, raw_path, _version = first.decode("ascii").split(" ", 2)
            except (UnicodeDecodeError, ValueError):
                await self._send(writer, 400, "application/json", b'{"error":"bad_request"}')
                return
            if method != "GET":
                await self._send(
                    writer,
                    405,
                    "application/json",
                    b'{"error":"method_not_allowed"}',
                )
                return
            path = raw_path.split("?", 1)[0]
            if path == "/metrics":
                await self._send(
                    writer,
                    200,
                    CONTENT_TYPE_LATEST,
                    self.metrics.render(),
                )
                return
            if path not in {"/health/live", "/health/ready"}:
                await self._send(writer, 404, "application/json", b'{"error":"not_found"}')
                return
            snapshot = await self.snapshot_provider()
            body = json.dumps(
                {
                    "node_id": self.node_id,
                    "liveness": bool(snapshot.liveness),
                    "readiness": bool(snapshot.readiness),
                    "coordination": bool(snapshot.coordination),
                    "cluster": bool(snapshot.cluster),
                    "recovery_phase": str(
                        getattr(
                            snapshot.recovery_phase,
                            "value",
                            snapshot.recovery_phase,
                        )
                    ),
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
            healthy = bool(snapshot.liveness) if path.endswith("live") else bool(snapshot.readiness)
            await self._send(writer, 200 if healthy else 503, "application/json", body)
        except (TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            try:
                await self._send(writer, 400, "application/json", b'{"error":"bad_request"}')
            except (ConnectionError, RuntimeError):
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    @staticmethod
    async def _send(
        writer: asyncio.StreamWriter,
        status: int,
        content_type: str,
        body: bytes,
    ) -> None:
        reasons = {
            200: "OK",
            400: "Bad Request",
            404: "Not Found",
            405: "Method Not Allowed",
            431: "Request Header Fields Too Large",
            503: "Service Unavailable",
        }
        head = (
            f"HTTP/1.1 {status} {reasons.get(status, 'Error')}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "Cache-Control: no-store\r\n\r\n"
        ).encode("ascii")
        writer.write(head + body)
        await writer.drain()
