import asyncio
import json
from pathlib import Path
from typing import cast

from distsys.chaos.controller import ChaosController
from distsys.chaos.model import ProbeState
from distsys.chaos.safety import ManagedManifest
from distsys.chaos.toxiproxy import ToxiproxyClient


def _manifest(tmp_path: Path) -> ManagedManifest:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "runtime_dir": str(tmp_path),
                "pids": {},
                "proxies": [
                    "peer-node-0",
                    "peer-node-1",
                    "peer-node-2",
                    "etcd",
                ],
                "services": [
                    "etcd",
                    "node-0",
                    "node-1",
                    "node-2",
                ],
            }
        ),
        encoding="utf-8",
    )
    return ManagedManifest.load(path)


def test_node_kill_uses_scoped_compose_lifecycle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RUN_CHAOS_TESTS", "1")

    states = iter(
        (
            ProbeState(
                ready_nodes=("node-0", "node-1", "node-2"),
                coordination_healthy_nodes=("node-0", "node-1", "node-2"),
                target_reachable=True,
                peer_latency_seconds=0.01,
                data_plane_ok=True,
            ),
            ProbeState(
                ready_nodes=("node-0", "node-2"),
                coordination_healthy_nodes=("node-0", "node-2"),
                target_reachable=False,
                peer_latency_seconds=None,
                data_plane_ok=True,
            ),
            ProbeState(
                ready_nodes=("node-0", "node-1", "node-2"),
                coordination_healthy_nodes=("node-0", "node-1", "node-2"),
                target_reachable=True,
                peer_latency_seconds=0.01,
                data_plane_ok=True,
            ),
        )
    )

    async def probe() -> ProbeState:
        return next(states)

    controller = ChaosController(
        _manifest(tmp_path),
        cast(ToxiproxyClient, object()),
        probe,
    )

    compose_calls: list[tuple[str, ...]] = []

    async def fake_compose(*args: str) -> None:
        compose_calls.append(args)

    monkeypatch.setattr(controller, "_compose", fake_compose)

    result = asyncio.run(
        controller.run(
            "node-kill",
            target="node-1",
            max_seconds=5.0,
        )
    )

    assert result.passed
    assert compose_calls[0] == ("kill", "node-1")
    assert ("start", "node-1") in compose_calls

    # Cleanup is intentionally idempotent and may call start again.
    assert all(
        call
        in {
            ("kill", "node-1"),
            ("start", "node-1"),
        }
        for call in compose_calls
    )


def test_node_kill_rejects_service_outside_managed_nodes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RUN_CHAOS_TESTS", "1")

    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "runtime_dir": str(tmp_path),
                "pids": {},
                "proxies": [],
                "services": ["etcd"],
            }
        ),
        encoding="utf-8",
    )

    async def probe() -> ProbeState:
        return ProbeState(
            ready_nodes=("node-0", "node-1", "node-2"),
            coordination_healthy_nodes=("node-0", "node-1", "node-2"),
            target_reachable=True,
            peer_latency_seconds=0.01,
            data_plane_ok=True,
        )

    controller = ChaosController(
        ManagedManifest.load(path),
        cast(ToxiproxyClient, object()),
        probe,
    )

    compose_calls: list[tuple[str, ...]] = []

    async def fake_compose(*args: str) -> None:
        compose_calls.append(args)

    monkeypatch.setattr(controller, "_compose", fake_compose)

    result = asyncio.run(
        controller.run(
            "node-kill",
            target="node-1",
            max_seconds=5.0,
        )
    )

    assert not result.passed
    assert compose_calls == []
    assert "not a managed Phase 6 node service" in result.observed_effect
