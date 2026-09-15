from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase7_runbooks_are_complete_and_honest() -> None:
    docs = "\n".join(path.read_text() for path in (ROOT / "docs/runbooks").glob("phase7-*.md"))
    assert "make phase7-release-gate" in docs
    assert "PENDING SEPARATE APPROVAL" in docs
    assert "no NAT Gateway" in docs
    assert "port-forward" in docs
    assert "USD 15" in docs
    assert "OIDC" in docs
    assert "does not prove consensus" in docs


def test_verification_status_does_not_claim_aws() -> None:
    text = (ROOT / "docs/verification/phase7.md").read_text()
    assert (
        "Local Kubernetes delivery implemented and verified; AWS EKS demonstration pending." in text
    )
    assert "No AWS resource creation is claimed" in text
    assert "PENDING SEPARATE APPROVAL" in text
