"""Environment-based Phase-1 settings."""

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

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            node_id=os.getenv("NODE_ID", "node-0"),
            host=os.getenv("NODE_HOST", "127.0.0.1"),
            port=int(os.getenv("NODE_PORT", "8000")),
            max_frame_size=int(os.getenv("MAX_FRAME_SIZE", str(DEFAULT_MAX_FRAME_SIZE))),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5.0")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
