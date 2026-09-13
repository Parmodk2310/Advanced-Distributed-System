from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from distsys.coordination.errors import CoordinationUnavailableError
from distsys.coordination.etcd_client import EtcdGatewayCoordinationClient
from tests.integration.etcd_helpers import require_etcd_integration


async def run_compose(compose: Path, *args: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "-f",
        str(compose),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"docker compose {' '.join(args)} failed: {detail}")


@pytest.mark.asyncio
@pytest.mark.etcd
async def test_real_etcd_outage_then_client_recovery():
    endpoints = require_etcd_integration()
    root = Path(__file__).resolve().parents[2]
    compose = root / "docker" / "etcd" / "docker-compose.yml"

    healthy = EtcdGatewayCoordinationClient(endpoints, namespace="/distsys/outage-test")
    await healthy.connect()
    await healthy.close()

    await run_compose(compose, "stop", "etcd")
    try:
        await asyncio.sleep(0.5)
        unavailable = EtcdGatewayCoordinationClient(
            endpoints,
            namespace="/distsys/outage-test",
            timeout_seconds=0.5,
        )
        with pytest.raises(CoordinationUnavailableError):
            await unavailable.connect()
    finally:
        await run_compose(compose, "start", "etcd")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + 10.0
    while True:
        recovered = EtcdGatewayCoordinationClient(
            endpoints,
            namespace="/distsys/outage-test",
            timeout_seconds=1.0,
        )
        try:
            await recovered.connect()
            await recovered.close()
            break
        except CoordinationUnavailableError:
            if loop.time() >= deadline:
                raise
            await asyncio.sleep(0.25)
