"""Environment-based distributed-system settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from distsys.protocol.framing import DEFAULT_MAX_FRAME_SIZE


@dataclass(slots=True, frozen=True)
class Settings:
    node_id: str = "node-0"
    host: str = "127.0.0.1"
    port: int = 8000
    max_frame_size: int = DEFAULT_MAX_FRAME_SIZE
    request_timeout_seconds: float = 5.0
    log_level: str = "INFO"

    cpu_workers: int = 2
    cpu_queue_capacity: int = 200
    rate_limit_rps: float = 500.0
    rate_limit_burst: int = 100

    retry_max_attempts: int = 3
    retry_base_delay_seconds: float = 0.05
    retry_max_delay_seconds: float = 1.0

    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.cpu_workers < 1:
            raise ValueError("cpu_workers must be at least 1")
        if self.cpu_queue_capacity < 1:
            raise ValueError("cpu_queue_capacity must be at least 1")
        if self.rate_limit_rps <= 0:
            raise ValueError("rate_limit_rps must be greater than zero")
        if self.rate_limit_burst < 1:
            raise ValueError("rate_limit_burst must be at least 1")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be greater than zero")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            node_id=os.getenv("NODE_ID", "node-0"),
            host=os.getenv("NODE_HOST", "127.0.0.1"),
            port=int(os.getenv("NODE_PORT", "8000")),
            max_frame_size=int(os.getenv("MAX_FRAME_SIZE", str(DEFAULT_MAX_FRAME_SIZE))),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5.0")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            cpu_workers=int(os.getenv("CPU_WORKERS", "2")),
            cpu_queue_capacity=int(os.getenv("CPU_QUEUE_CAPACITY", "200")),
            rate_limit_rps=float(os.getenv("RATE_LIMIT_RPS", "500.0")),
            rate_limit_burst=int(os.getenv("RATE_LIMIT_BURST", "100")),
            retry_max_attempts=int(os.getenv("RETRY_MAX_ATTEMPTS", "3")),
            retry_base_delay_seconds=float(os.getenv("RETRY_BASE_DELAY_SECONDS", "0.05")),
            retry_max_delay_seconds=float(os.getenv("RETRY_MAX_DELAY_SECONDS", "1.0")),
            circuit_breaker_failure_threshold=int(
                os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
            ),
            circuit_breaker_recovery_seconds=float(
                os.getenv("CIRCUIT_BREAKER_RECOVERY_SECONDS", "10.0")
            ),
        )
