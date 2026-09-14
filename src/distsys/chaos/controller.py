"""Guarded, assertion-driven Phase 6 chaos scenario controller."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from collections.abc import Awaitable, Callable

from distsys.chaos.model import ProbeState, ScenarioResult, utc_now
from distsys.chaos.safety import (
    CleanupStack,
    ManagedManifest,
    require_chaos_opt_in,
    validate_duration,
    validate_pid,
)
from distsys.chaos.toxiproxy import ToxiproxyClient

Probe = Callable[[], Awaitable[ProbeState]]


class ChaosController:
    COMPOSE = (
        "docker",
        "compose",
        "-p",
        "distsys-phase6",
        "-f",
        "deploy/monitoring/docker-compose.yml",
    )
    SCENARIOS = frozenset({"node-kill", "network-delay", "partition", "etcd-outage"})

    def __init__(self, manifest: ManagedManifest, toxiproxy: ToxiproxyClient, probe: Probe) -> None:
        self.manifest = manifest
        self.toxiproxy = toxiproxy
        self.probe = probe

    async def _restart_managed(self, target: str) -> None:
        process = self.manifest.pids.get(target)
        if process is None or not process.restart_argv:
            raise ValueError(f"managed node {target} has no restart command")
        argv = process.restart_argv
        if (
            len(argv) < 3
            or argv[0] != "bash"
            or argv[1] != "scripts/phase6_start_node.sh"
            or argv[2] != target
        ):
            raise ValueError("restart command is outside the Phase 6 managed launcher")
        proc = await asyncio.create_subprocess_exec(*argv)
        if await proc.wait() != 0:
            raise RuntimeError(f"managed restart failed for {target}")

    async def _compose(self, *args: str) -> None:
        proc = await asyncio.create_subprocess_exec(*self.COMPOSE, *args)
        code = await proc.wait()
        if code != 0:
            raise RuntimeError(f"scoped docker compose command failed: {args}")

    async def _await_state(
        self,
        predicate: Callable[[ProbeState], bool],
        *,
        timeout_seconds: float,
        description: str,
    ) -> ProbeState:
        deadline = time.monotonic() + timeout_seconds
        last: ProbeState | None = None
        while time.monotonic() < deadline:
            last = await self.probe()
            if predicate(last):
                return last
            await asyncio.sleep(0.25)
        detail = last.to_dict() if last is not None else None
        raise AssertionError(f"timed out waiting for {description}; last={detail}")

    async def run(
        self,
        scenario: str,
        *,
        max_seconds: float = 30.0,
        target: str = "node-1",
    ) -> ScenarioResult:
        require_chaos_opt_in()
        if scenario not in self.SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}")
        validate_duration(max_seconds, maximum_seconds=120.0)

        cleanup = CleanupStack()
        started_utc = utc_now()
        expected = ""
        observations: dict[str, object] = {}
        passed = False
        recovery_seconds = 0.0
        cleanup_ok = False
        failure: str | None = None

        try:
            async with asyncio.timeout(max_seconds):
                baseline = await self._await_state(
                    lambda s: s.data_plane_ok and len(s.ready_nodes) == 3 and s.target_reachable,
                    timeout_seconds=min(8.0, max_seconds / 3),
                    description="healthy three-node baseline",
                )
                observations["baseline"] = baseline.to_dict()

                if scenario == "network-delay":
                    expected = "peer RTT increases while the local data plane stays healthy, then returns to baseline"
                    proxy = f"peer-{target}"
                    if not self.manifest.has_proxy(proxy):
                        raise ValueError(f"unmanaged proxy: {proxy}")
                    toxic = "phase6-latency"
                    cleanup.push(lambda: self.toxiproxy.remove_toxic(proxy, toxic))
                    await self.toxiproxy.add_latency(proxy, toxic, latency_ms=250, jitter_ms=25)
                    degraded = await self._await_state(
                        lambda s: s.data_plane_ok
                        and s.target_reachable
                        and s.peer_latency_seconds is not None
                        and s.peer_latency_seconds >= 0.18,
                        timeout_seconds=6.0,
                        description="bounded peer latency injection",
                    )
                    observations["degraded"] = degraded.to_dict()
                    recovery_started = time.perf_counter()
                    await self.toxiproxy.remove_toxic(proxy, toxic)
                    baseline_latency = baseline.peer_latency_seconds or 0.0
                    recovery_limit = max(0.18, baseline_latency * 1.5)
                    recovered = await self._await_state(
                        lambda s: s.data_plane_ok
                        and s.target_reachable
                        and s.peer_latency_seconds is not None
                        and s.peer_latency_seconds < recovery_limit,
                        timeout_seconds=6.0,
                        description="peer latency recovery",
                    )

                elif scenario == "partition":
                    expected = "selected peer path becomes unreachable while local work continues, then reconnects"
                    proxy = f"peer-{target}"
                    if not self.manifest.has_proxy(proxy):
                        raise ValueError(f"unmanaged proxy: {proxy}")
                    cleanup.push(lambda: self.toxiproxy.set_enabled(proxy, True))
                    await self.toxiproxy.set_enabled(proxy, False)
                    degraded = await self._await_state(
                        lambda s: s.data_plane_ok and not s.target_reachable,
                        timeout_seconds=6.0,
                        description="selected peer partition",
                    )
                    observations["degraded"] = degraded.to_dict()
                    recovery_started = time.perf_counter()
                    await self.toxiproxy.set_enabled(proxy, True)
                    recovered = await self._await_state(
                        lambda s: s.data_plane_ok and s.target_reachable,
                        timeout_seconds=8.0,
                        description="peer partition recovery",
                    )

                elif scenario == "etcd-outage":
                    expected = "coordination reports unhealthy while existing data-plane work continues, then leases recover"
                    if not self.manifest.has_service("etcd"):
                        raise ValueError("etcd is not a managed Phase 6 service")
                    cleanup.push(lambda: self._compose("start", "etcd"))
                    await self._compose("stop", "etcd")
                    degraded = await self._await_state(
                        lambda s: s.data_plane_ok and len(s.coordination_healthy_nodes) < 3,
                        timeout_seconds=12.0,
                        description="coordination degradation after etcd outage",
                    )
                    observations["degraded"] = degraded.to_dict()
                    recovery_started = time.perf_counter()
                    await self._compose("start", "etcd")
                    recovered = await self._await_state(
                        lambda s: s.data_plane_ok and len(s.coordination_healthy_nodes) == 3,
                        timeout_seconds=12.0,
                        description="coordination recovery after etcd restart",
                    )

                else:
                    expected = "one managed node stops, two-node service continuity is preserved, then the node restarts"
                    process = self.manifest.pids.get(target)
                    if process is None:
                        raise ValueError(f"unknown managed node: {target}")
                    validate_pid(process.pid, self.manifest)
                    cleanup.push(lambda: self._restart_managed(target))
                    os.kill(process.pid, signal.SIGKILL)
                    degraded = await self._await_state(
                        lambda s: s.data_plane_ok
                        and target not in s.ready_nodes
                        and not s.target_reachable
                        and len(s.ready_nodes) >= 2,
                        timeout_seconds=8.0,
                        description="managed node termination with remaining service continuity",
                    )
                    observations["degraded"] = degraded.to_dict()
                    recovery_started = time.perf_counter()
                    await asyncio.sleep(0.25)
                    await self._restart_managed(target)
                    recovered = await self._await_state(
                        lambda s: s.data_plane_ok
                        and target in s.ready_nodes
                        and s.target_reachable
                        and len(s.ready_nodes) == 3,
                        timeout_seconds=12.0,
                        description="managed node restart and cluster readiness",
                    )

                recovery_seconds = time.perf_counter() - recovery_started
                observations["recovered"] = recovered.to_dict()
                passed = True
        except Exception as exc:  # noqa: BLE001 - record scenario failure
            failure = f"{type(exc).__name__}: {exc}"
            observations["failure"] = failure
        finally:
            errors = await cleanup.run()
            cleanup_ok = not errors
            if errors:
                observations["cleanup_errors"] = [f"{type(e).__name__}: {e}" for e in errors]

        return ScenarioResult(
            scenario=scenario,
            started_utc=started_utc,
            ended_utc=utc_now(),
            expected_effect=expected or "bounded, observable degradation followed by recovery",
            observed_effect=json.dumps(observations, sort_keys=True, separators=(",", ":")),
            recovery_seconds=recovery_seconds,
            cleanup_ok=cleanup_ok,
            passed=passed and cleanup_ok and failure is None,
        )
