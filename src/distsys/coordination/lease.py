"""Background etcd lease lifecycle."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from distsys.coordination.client import CoordinationClient
from distsys.coordination.errors import CoordinationUnavailableError
from distsys.coordination.models import CoordinationHealth, CoordinationMember, LeaseHandle

logger = logging.getLogger("distsys.coordination.lease")


class LeaseManager:
    def __init__(
        self,
        client: CoordinationClient,
        *,
        ttl_seconds: int = 15,
        renew_interval_seconds: float = 5.0,
        on_health_change: Callable[[CoordinationHealth], Awaitable[None]] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if renew_interval_seconds <= 0 or renew_interval_seconds >= ttl_seconds:
            raise ValueError("renew interval must be positive and less than lease TTL")
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.renew_interval_seconds = renew_interval_seconds
        self._member: CoordinationMember | None = None
        self._lease: LeaseHandle | None = None
        self._task: asyncio.Task[None] | None = None
        self._on_health_change = on_health_change
        self.health = CoordinationHealth(False, False, None, "not started")

    async def _publish_health(self, health: CoordinationHealth) -> None:
        self.health = health
        if self._on_health_change is not None:
            await self._on_health_change(health)

    async def _acquire_and_register(self) -> None:
        member = self._member
        if member is None:
            raise RuntimeError("lease manager member is not configured")
        lease = await self.client.grant_lease(self.ttl_seconds)
        await self.client.register_member(member, lease)
        self._lease = lease
        await self._publish_health(CoordinationHealth(True, True, lease.lease_id, "healthy"))
        logger.info(
            "etcd lease granted",
            extra={"event": "etcd_lease_granted", "lease_id": lease.lease_id},
        )

    async def start(self, member: CoordinationMember) -> None:
        if self._task is not None:
            return
        self._member = member
        await self._acquire_and_register()
        self._task = asyncio.create_task(self._loop(), name="etcd-lease-renewal")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._publish_health(CoordinationHealth(False, False, None, "stopped"))

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.renew_interval_seconds)
            try:
                if self._lease is None:
                    await self._acquire_and_register()
                else:
                    await self.client.refresh_lease(self._lease)
                    await self._publish_health(
                        CoordinationHealth(True, True, self._lease.lease_id, "healthy")
                    )
                    logger.debug(
                        "etcd lease renewed",
                        extra={
                            "event": "etcd_lease_renewed",
                            "lease_id": self._lease.lease_id,
                        },
                    )
            except asyncio.CancelledError:
                raise
            except (
                CoordinationUnavailableError,
                ConnectionError,
                TimeoutError,
                OSError,
                RuntimeError,
            ) as exc:
                self._lease = None
                await self._publish_health(CoordinationHealth(False, False, None, str(exc)))
                logger.warning(
                    "etcd lease lost",
                    extra={"event": "etcd_lease_lost", "error": str(exc)},
                )
                # Next iteration attempts a fresh lease and registration.
