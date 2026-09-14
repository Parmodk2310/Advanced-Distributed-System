import asyncio
import json
from dataclasses import dataclass
from enum import Enum

import pytest


class RecoveryPhase(str, Enum):
    RECONCILING = "reconciling"
    READY = "ready"


@dataclass(frozen=True)
class NodeHealthSnapshot:
    liveness: bool = True
    readiness: bool = False
    coordination: bool = False
    cluster: bool = False
    recovery_phase: RecoveryPhase = RecoveryPhase.READY
    coordination_message: str = ""
    last_error: str = ""


from distsys.observability.health import ObservabilityServer
from distsys.observability.metrics import Metrics


async def _get(port: int, path: str) -> tuple[int, dict[str, str], bytes]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(
        (f"GET {path} HTTP/1.1\r\n" "Host: localhost\r\n" "Connection: close\r\n\r\n").encode()
    )
    await writer.drain()
    raw = await reader.read()
    writer.close()
    await writer.wait_closed()
    head, body = raw.split(b"\r\n\r\n", 1)
    lines = head.decode().split("\r\n")
    status = int(lines[0].split()[1])
    headers = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
    return status, headers, body


@pytest.mark.asyncio
async def test_ready_route_tracks_snapshot_and_hides_internal_details():
    state = NodeHealthSnapshot(
        liveness=True,
        readiness=False,
        coordination=True,
        cluster=True,
        recovery_phase=RecoveryPhase.RECONCILING,
        coordination_message="do-not-expose",
        last_error="secret traceback",
    )

    async def snapshot():
        return state

    server = ObservabilityServer("127.0.0.1", 0, "node-a", Metrics("node-a"), snapshot)
    await server.start()
    try:
        status, headers, body = await _get(server.bound_port, "/health/ready")
        assert status == 503
        assert headers["Content-Type"] == "application/json"
        payload = json.loads(body)
        assert payload == {
            "node_id": "node-a",
            "liveness": True,
            "readiness": False,
            "coordination": True,
            "cluster": True,
            "recovery_phase": "reconciling",
        }
        assert b"secret" not in body and b"do-not-expose" not in body
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_metrics_live_not_found_and_method_not_allowed():
    async def snapshot():
        return NodeHealthSnapshot(readiness=True, recovery_phase=RecoveryPhase.READY)

    metrics = Metrics("node-a")
    server = ObservabilityServer("127.0.0.1", 0, "node-a", metrics, snapshot)
    await server.start()
    try:
        status, _, body = await _get(server.bound_port, "/health/live")
        assert status == 200
        assert json.loads(body)["liveness"] is True
        status, headers, body = await _get(server.bound_port, "/metrics")
        assert status == 200
        assert headers["Content-Type"].startswith("text/plain")
        assert b"distsys_" in body
        status, _, _ = await _get(server.bound_port, "/missing")
        assert status == 404
    finally:
        await server.stop()
