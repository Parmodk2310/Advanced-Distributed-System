from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_hardened_container_contract():
    docker = (ROOT / "Dockerfile").read_text()
    ignore = (ROOT / ".dockerignore").read_text()
    from_lines = [line for line in docker.splitlines() if line.startswith("FROM ")]

    assert len(from_lines) == 2
    assert all("@sha256:" in line for line in from_lines)
    assert docker.count(" AS ") >= 2
    assert "USER 10001:10001" in docker
    assert 'ENTRYPOINT ["python", "-m", "distsys.main"]' in docker
    assert "EXPOSE 8000 9100" in docker
    for item in (".git", ".venv", "tests", "certs", "*.tfstate", ".phase7"):
        assert item in ignore
