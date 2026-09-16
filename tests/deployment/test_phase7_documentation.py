from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_phase7_docs_state_cloud_limit_and_release_gates() -> None:
    verification = read("docs/verification/phase7.md")
    aws_runbook = read("docs/runbooks/phase7-aws-demonstration.md")

    assert "Phase 7B" in verification
    assert "No AWS resource is created" in verification
    assert "v0.7.0" in verification

    assert "not node/AZ-level HA" in aws_runbook
