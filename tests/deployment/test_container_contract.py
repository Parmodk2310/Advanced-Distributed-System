from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"


def _dockerfile() -> str:
    assert DOCKERFILE.is_file(), "Dockerfile must exist at the repository root"
    return DOCKERFILE.read_text(encoding="utf-8")


def test_runtime_image_is_pinned_and_multi_stage() -> None:
    dockerfile = _dockerfile()
    from_lines = [line.strip() for line in dockerfile.splitlines() if line.startswith("FROM ")]

    assert len(from_lines) == 2
    assert all("python:3.12.11-slim-bookworm@sha256:" in line for line in from_lines)
    assert all(re.search(r"@sha256:[0-9a-f]{64}(?:\s+AS\s+\w+)?$", line) for line in from_lines)
    assert from_lines[0].endswith(" AS builder")
    assert from_lines[1].endswith(" AS runtime")


def test_runtime_uses_non_root_identity_and_expected_entrypoint() -> None:
    dockerfile = _dockerfile()
    runtime_stage = dockerfile.split(" AS runtime", maxsplit=1)[1]

    assert "USER 10001:10001" in dockerfile
    assert 'ENTRYPOINT ["python", "-m", "distsys.main"]' in dockerfile
    assert "EXPOSE 8000 9100" in dockerfile
    assert "COPY --from=builder /wheelhouse /wheelhouse" in dockerfile
    assert "COPY src" not in runtime_stage


def test_runtime_applies_available_base_os_security_updates() -> None:
    runtime_stage = _dockerfile().split(" AS runtime", maxsplit=1)[1]
    assert "apt-get update" in runtime_stage
    assert "apt-get upgrade -y" in runtime_stage
    assert "rm -rf /var/lib/apt/lists/*" in runtime_stage


def test_runtime_has_only_explicit_writable_paths() -> None:
    dockerfile = _dockerfile()

    assert 'VOLUME ["/data"]' in dockerfile
    assert "TMPDIR=/tmp" in dockerfile
    assert "chown -R 10001:10001 /data /tmp" in dockerfile


def test_docker_context_excludes_local_and_sensitive_artifacts() -> None:
    assert DOCKERIGNORE.is_file(), ".dockerignore must exist at the repository root"
    ignored = {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    required = {
        ".git",
        ".venv",
        "certs",
        "tests",
        "*.db",
        "*.db-wal",
        "*.db-shm",
        "*.tfstate",
        "*.tfplan",
        ".phase7",
    }
    assert required <= ignored
