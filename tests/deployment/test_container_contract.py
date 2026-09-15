from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"


def test_runtime_image_contract_is_hardened() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")

    assert len(re.findall(r"^FROM ", text, flags=re.MULTILINE)) == 2
    assert re.search(
        r"^FROM python:3\.12-slim@sha256:[0-9a-f]{64} AS builder$",
        text,
        flags=re.MULTILINE,
    )
    assert re.search(
        r"^FROM python:3\.12-slim@sha256:[0-9a-f]{64} AS runtime$",
        text,
        flags=re.MULTILINE,
    )
    assert "USER 10001:10001" in text
    assert "EXPOSE 8000 9100" in text
    assert 'ENTRYPOINT ["python", "-m", "distsys.main"]' in text


def test_runtime_image_does_not_copy_source_tree() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    runtime = text.split(" AS runtime", maxsplit=1)[1]

    assert "COPY --from=builder /wheelhouse/" in runtime
    assert "COPY src " not in runtime
    assert "COPY tests " not in runtime
    assert "COPY certs " not in runtime


def test_build_context_excludes_sensitive_and_generated_files() -> None:
    ignored = {
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    required = {
        ".git",
        ".venv",
        ".phase7",
        "certs/generated",
        "*.db",
        "*.sqlite*",
        "*.tfstate*",
        "*.tfplan",
        "tests",
    }
    assert required <= ignored


def test_image_declares_expected_entrypoint_as_json() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    match = re.search(r"^ENTRYPOINT (\[.*\])$", text, flags=re.MULTILINE)

    assert match is not None
    assert json.loads(match.group(1)) == ["python", "-m", "distsys.main"]
