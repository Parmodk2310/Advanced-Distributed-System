"""Asynchronous fast-path CRDT state replication workers."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from distsys.protocol.errors import ProtocolError
from distsys.replication.outbox import PendingReplication, ReplicationOutbox
from distsys.replication.peer_client import CrdtRemoteError
from distsys.resilience.retry import RetryPolicy, retry_async
from distsys.storage import StoredCrdtEntry

logger = logging.getLogger("distsys.replication.replicator")

_RETRYABLE = (ConnectionError, TimeoutError, OSError)
_EXPECTED_SEND_FAILURES = (*_RETRYABLE, CrdtRemoteError, ProtocolError)


class ReplicationPeerTransport(Protocol):
    async def send_state(self, peer_node_id: str, state: StoredCrdtEntry) -> None: ...


class Replicator:
    def __init__(
        self,
        outbox: ReplicationOutbox,
        transport: ReplicationPeerTransport,
        *,
        worker_count: int = 2,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if worker_count < 1:
            raise ValueError("worker_count must be >= 1")
        self.outbox = outbox
        self.transport = transport
        self.worker_count = worker_count
        self.retry_policy = retry_policy or RetryPolicy()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(self._worker(), name=f"crdt-replicator-{index}")
            for index in range(self.worker_count)
        ]

    async def stop(self) -> None:
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_with_retry(self, item: PendingReplication) -> None:
        async def attempt() -> None:
            await self.transport.send_state(item.peer_node_id, item.state)

        await retry_async(
            attempt,
            policy=self.retry_policy,
            should_retry=lambda exc: isinstance(exc, _RETRYABLE),
        )

    async def _worker(self) -> None:
        while True:
            item = await self.outbox.next_ready()
            try:
                await self._send_with_retry(item)
            except asyncio.CancelledError:
                # Preserve pending work in-memory while stopping; the process is
                # shutting down and anti-entropy is the eventual repair path.
                await self.outbox.abandon(item.peer_node_id, item.key, item.generation)
                raise
            except _EXPECTED_SEND_FAILURES:
                logger.warning(
                    "crdt replication retry exhausted",
                    extra={
                        "event": "crdt_replication_retry_exhausted",
                        "peer_id": item.peer_node_id,
                        "key": item.key,
                    },
                )
                await self.outbox.abandon(item.peer_node_id, item.key, item.generation)
            else:
                logger.debug(
                    "crdt replication sent",
                    extra={
                        "event": "crdt_replication_sent",
                        "peer_id": item.peer_node_id,
                        "key": item.key,
                    },
                )
                await self.outbox.complete(item.peer_node_id, item.key, item.generation)
