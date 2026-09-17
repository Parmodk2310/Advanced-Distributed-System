from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "docs/design/phase7-production-delivery.md"


def test_phase7_design_preserves_detailed_engineering_boundaries() -> None:
    text = DESIGN.read_text(encoding="utf-8")

    for required in (
        "## Explicit non-goals and non-guarantees",
        "linearizability",
        "quorum durability",
        "exactly-once execution",
        "permanent production hosting",
        "Phase 7B was outside the initial implementation authority",
        "No AWS resource is created merely by committing",
    ):
        assert required in text


def test_phase7_design_keeps_current_delivery_flow_and_truthful_status() -> None:
    text = DESIGN.read_text(encoding="utf-8")

    assert "```mermaid" in text
    assert "Build OCI image once" in text
    assert "Separate AWS approval" in text
    assert "Copy exact artifact to ECR - no rebuild" in text
    assert "single-worker EKS demonstration" in text

    normalized = " ".join(text.split())
    assert "multi-node or multi-AZ etcd HA" in normalized

    assert "APPROVED DESIGN — NOT IMPLEMENTED" not in text
    assert "phase 7b temporary aws eks lifecycle verified" in normalized.lower()
    assert "does not establish permanent production or multi-AZ readiness" in text
