"""Serializable benchmark contracts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    profile: str = "laptop"
    workload: str = "task"
    concurrency: int = 16
    warmup_seconds: float = 10.0
    duration_seconds: float = 30.0
    payload_size: int = 256
    read_ratio: float = 0.8
    seed: int = 6

    def __post_init__(self) -> None:
        if self.profile not in {"quick", "laptop", "formal"}:
            raise ValueError("profile must be quick, laptop, or formal")
        if self.workload not in {"task", "crdt"}:
            raise ValueError("workload must be task or crdt")
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if self.warmup_seconds < 0 or self.duration_seconds <= 0:
            raise ValueError("benchmark timing must be non-negative/positive")
        if self.payload_size < 0:
            raise ValueError("payload_size cannot be negative")
        if not 0.0 <= self.read_ratio <= 1.0:
            raise ValueError("read_ratio must be in [0.0, 1.0]")


@dataclass(frozen=True, slots=True)
class LatencySummary:
    p50_seconds: float
    p95_seconds: float
    p99_seconds: float
    max_seconds: float


@dataclass(frozen=True, slots=True)
class CorrectnessCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    timestamp_utc: str
    git_commit: str
    git_dirty: bool
    environment: dict[str, Any]
    config: BenchmarkConfig
    successes: int
    failures: dict[str, int]
    throughput_rps: float
    latency: LatencySummary
    correctness: tuple[CorrectnessCheck, ...] = field(default_factory=tuple)

    @property
    def request_count(self) -> int:
        return self.successes + sum(self.failures.values())

    @property
    def valid(self) -> bool:
        return not self.failures and all(check.passed for check in self.correctness)

    @property
    def success_ratio(self) -> float:
        return self.successes / self.request_count if self.request_count else 0.0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["request_count"] = self.request_count
        value["success_ratio"] = self.success_ratio
        value["valid"] = self.valid
        return value

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
