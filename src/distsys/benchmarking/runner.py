"""Bounded-concurrency benchmark executor with environment evidence."""

from __future__ import annotations

import asyncio
import os
import platform
import random
import subprocess
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from distsys.benchmarking.model import (
    BenchmarkConfig,
    BenchmarkResult,
    CorrectnessCheck,
)
from distsys.benchmarking.stats import latency_summary

TaskCall = Callable[[int, bytes], Awaitable[Any]]
CrdtCall = Callable[[int, bool], Awaitable[Any]]


def _git(args: list[str], default: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return default


def environment_metadata() -> dict[str, Any]:
    release = platform.release()
    version = platform.version()
    is_wsl = "microsoft" in release.lower() or "microsoft" in version.lower()
    is_container = os.path.exists("/.dockerenv") or os.getenv("container") is not None
    memory_bytes = 0
    try:
        with open("/proc/meminfo", encoding="utf-8") as meminfo:
            for line in meminfo:
                if line.startswith("MemTotal:"):
                    memory_bytes = int(line.split()[1]) * 1024
                    break
    except OSError:
        pass
    return {
        "python": platform.python_version(),
        "os": platform.system(),
        "kernel": release,
        "machine": platform.machine(),
        "logical_cores": os.cpu_count() or 1,
        "memory_bytes": memory_bytes,
        "wsl": is_wsl,
        "container": is_container,
    }


class BenchmarkRunner:
    def __init__(
        self,
        *,
        task_call: TaskCall | None = None,
        crdt_call: CrdtCall | None = None,
    ) -> None:
        self.task_call = task_call
        self.crdt_call = crdt_call

    async def run(self, config: BenchmarkConfig) -> BenchmarkResult:
        rng = random.Random(config.seed)
        payload = bytes(rng.randrange(0, 256) for _ in range(config.payload_size))
        stop = asyncio.Event()
        collect = asyncio.Event()
        latencies: list[float] = []
        failures: Counter[str] = Counter()
        successes = 0
        sequence = 0
        lock = asyncio.Lock()
        correctness: list[CorrectnessCheck] = []

        async def one(seq: int) -> None:
            nonlocal successes
            started = time.perf_counter_ns()
            try:
                if config.workload == "task":
                    if self.task_call is None:
                        raise RuntimeError("task callback is not configured")
                    result = await self.task_call(seq, payload)
                    if result is None:
                        raise AssertionError("task returned no result")
                else:
                    if self.crdt_call is None:
                        raise RuntimeError("CRDT callback is not configured")
                    is_read = random.Random(config.seed ^ seq).random() < config.read_ratio
                    result = await self.crdt_call(seq, is_read)
                    if result is None:
                        raise AssertionError("CRDT operation returned no result")
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                if collect.is_set():
                    failures["timeout"] += 1
            except AssertionError:
                if collect.is_set():
                    failures["correctness"] += 1
            except (ConnectionError, OSError):
                if collect.is_set():
                    failures["transport"] += 1
            except Exception:  # noqa: BLE001
                if collect.is_set():
                    failures["other"] += 1
            else:
                if collect.is_set():
                    successes += 1
            finally:
                if collect.is_set():
                    latencies.append((time.perf_counter_ns() - started) / 1_000_000_000)

        async def worker() -> None:
            nonlocal sequence
            while not stop.is_set():
                async with lock:
                    sequence += 1
                    seq = sequence
                await one(seq)

        tasks = [asyncio.create_task(worker()) for _ in range(config.concurrency)]
        try:
            if config.warmup_seconds:
                await asyncio.sleep(config.warmup_seconds)
            collect.set()
            measured_start = time.perf_counter()
            await asyncio.sleep(config.duration_seconds)
            elapsed = max(time.perf_counter() - measured_start, 1e-9)
            collect.clear()
            stop.set()
            await asyncio.gather(*tasks)
        finally:
            stop.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if failures.get("correctness", 0):
            correctness.append(
                CorrectnessCheck(
                    "workload_semantics",
                    False,
                    "one or more assertions failed",
                )
            )
        else:
            correctness.append(
                CorrectnessCheck(
                    "workload_semantics",
                    True,
                    "all measured responses satisfied checks",
                )
            )

        commit = _git(["rev-parse", "HEAD"], "unknown")
        dirty = _git(["status", "--porcelain"], "") != ""
        return BenchmarkResult(
            timestamp_utc=(
                datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            ),
            git_commit=commit,
            git_dirty=dirty,
            environment=environment_metadata(),
            config=config,
            successes=successes,
            failures=dict(sorted(failures.items())),
            throughput_rps=successes / elapsed,
            latency=latency_summary(latencies),
            correctness=tuple(correctness),
        )
