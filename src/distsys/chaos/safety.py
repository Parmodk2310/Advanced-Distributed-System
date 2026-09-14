"""Safety gates shared by every chaos scenario."""

from __future__ import annotations

import inspect
import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

Cleanup = Callable[[], Awaitable[None] | None]


def require_chaos_opt_in() -> None:
    if os.getenv("RUN_CHAOS_TESTS") != "1":
        raise PermissionError("chaos is disabled; set RUN_CHAOS_TESTS=1 explicitly")


def validate_duration(seconds: float, *, maximum_seconds: float) -> None:
    if seconds <= 0 or seconds > maximum_seconds:
        raise ValueError(f"duration must be > 0 and <= {maximum_seconds}")


@dataclass(frozen=True, slots=True)
class ManagedProcess:
    pid: int
    start_token: str
    cmdline_contains: str
    restart_argv: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ManagedManifest:
    runtime_dir: Path
    pids: dict[str, ManagedProcess]
    proxies: frozenset[str]
    services: frozenset[str]

    @classmethod
    def load(cls, path: str | Path) -> ManagedManifest:
        manifest_path = Path(path).resolve()
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        runtime_dir = Path(raw["runtime_dir"]).resolve()
        if (
            runtime_dir != manifest_path.parent.resolve()
            and runtime_dir not in manifest_path.parents
            and manifest_path.parent.resolve() != runtime_dir
        ):
            # Reject manifests that point cleanup actions at an unrelated host path.
            raise ValueError("manifest runtime_dir must contain the manifest")
        pids = {
            name: ManagedProcess(
                pid=int(item["pid"]),
                start_token=str(item["start_token"]),
                cmdline_contains=str(item["cmdline_contains"]),
                restart_argv=tuple(map(str, item.get("restart_argv", []))),
            )
            for name, item in raw.get("pids", {}).items()
        }
        return cls(
            runtime_dir=runtime_dir,
            pids=pids,
            proxies=frozenset(map(str, raw.get("proxies", []))),
            services=frozenset(map(str, raw.get("services", []))),
        )

    def has_proxy(self, name: str) -> bool:
        return name in self.proxies

    def has_service(self, name: str) -> bool:
        return name in self.services


def _proc_start_token(pid: int) -> str:
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    return stat.split()[21]


def _proc_cmdline(pid: int) -> str:
    return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")


def validate_pid(pid: int, manifest: ManagedManifest) -> str:
    matches = [(name, item) for name, item in manifest.pids.items() if item.pid == pid]
    if not matches:
        raise ValueError(f"PID {pid} is not managed by the Phase 6 manifest")
    name, expected = matches[0]
    try:
        actual_start = _proc_start_token(pid)
        actual_cmdline = _proc_cmdline(pid)
    except OSError as exc:
        raise ValueError(f"managed PID {pid} is no longer alive") from exc
    if expected.start_token and actual_start != expected.start_token:
        raise ValueError(f"PID {pid} was reused; start token mismatch")
    if expected.cmdline_contains and expected.cmdline_contains not in actual_cmdline:
        raise ValueError(f"PID {pid} command identity mismatch")
    return name


class CleanupStack:
    def __init__(self) -> None:
        self._actions: list[Cleanup] = []
        self._ran = False

    def push(self, action: Cleanup) -> None:
        if self._ran:
            raise RuntimeError("cleanup stack has already run")
        self._actions.append(action)

    async def run(self) -> list[BaseException]:
        if self._ran:
            return []
        self._ran = True
        errors: list[BaseException] = []
        while self._actions:
            action = self._actions.pop()
            try:
                result = action()
                if inspect.isawaitable(result):
                    await result
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
        return errors
