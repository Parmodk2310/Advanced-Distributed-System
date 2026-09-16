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


def test_phase7_aws_runbook_documents_temporary_runner_access() -> None:
    runbook = read("docs/runbooks/phase7-aws-demonstration.md")

    assert "eks:UpdateClusterConfig" in runbook
    assert "GitHub-hosted runner" in runbook
    assert "runner IPv4 address as a /32" in runbook
    assert "PHASE7_API_CIDRS_JSON" in runbook
    assert "always restores" in runbook
    assert "0.0.0.0/0" in runbook
