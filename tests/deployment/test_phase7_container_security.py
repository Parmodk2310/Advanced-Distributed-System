from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ALPINE_BASE = (
    "python:3.12.14-alpine3.24@sha256:"
    "b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a"
)


def test_phase7_image_uses_pinned_hardened_alpine_base() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.count(ALPINE_BASE) == 2
    assert dockerfile.count("apk upgrade --no-cache") >= 2

    assert "slim-bookworm" not in dockerfile
    assert "apt-get" not in dockerfile
