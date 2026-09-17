import tomllib
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


def test_phase7_aws_runbook_documents_delayed_storage_cleanup() -> None:
    runbook = read("docs/runbooks/phase7-aws-demonstration.md")

    assert "600 seconds" in runbook
    assert "Terraform state bucket and lock table" in runbook
    assert "EBS volumes" in runbook


def test_v070_package_metadata_describes_the_completed_system() -> None:
    metadata = tomllib.loads(read("pyproject.toml"))["project"]

    assert metadata["version"] == "0.7.0"
    assert metadata["description"] == (
        "Correctness-first distributed infrastructure for reliable AI/ML services"
    )
    assert "Phase 6" not in metadata["description"]


def test_release_docs_separate_demo_and_release_identity() -> None:
    readme = read("README.md")
    changelog = read("CHANGELOG.md")
    release_notes = read("docs/releases/v0.7.0.md")

    for document in (readme, changelog, release_notes):
        assert "Phase 7 AWS demonstration identity" in document
        assert "v0.7.0 release identity" in document

    assert "Immutable release identity" not in readme
