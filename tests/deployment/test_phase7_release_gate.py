from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def release_gate() -> str:
    return (ROOT / "scripts/phase7/release_gate.sh").read_text(encoding="utf-8")


def test_phase7_release_gate_covers_complete_local_delivery() -> None:
    gate = release_gate()

    required = (
        "pytest",
        "ruff",
        "black",
        "mypy",
        "compileall",
        "docker build",
        "helm lint",
        "kubeconform",
        "conftest",
        "trivy",
        "gitleaks",
        "syft",
        "terraform",
        "cluster_up.sh",
        "verify_cluster.py",
        "verify_persistence.py",
        "verify_rollback.sh",
        "cluster_down.sh",
    )

    missing = [item for item in required if item not in gate]

    assert not missing, "Phase 7 release gate is missing required stages: " + ", ".join(missing)


def test_phase7_release_gate_is_fail_closed_and_cleans_up() -> None:
    gate = release_gate()

    assert "set -euo pipefail" in gate
    assert "trap cleanup EXIT INT TERM" in gate
    assert "cluster_down.sh" in gate


def test_phase7_release_gate_records_no_aws_creation() -> None:
    gate = release_gate()

    assert '"aws_resources_created":false' in gate


def test_release_gate_does_not_reassign_common_readonly_image() -> None:
    gate = release_gate()

    assert "export PHASE7_IMAGE=" not in gate
    assert "readonly PHASE7_IMAGE=" not in gate


def test_phase7_release_gate_supplies_digest_for_eks_render() -> None:
    gate = release_gate()

    assert "--set-string image.repository=" in gate
    assert "--set-string image.digest=" in gate


def test_phase7_release_gate_deploys_the_already_verified_image() -> None:
    gate = release_gate()

    assert "export PHASE7_IMAGE" in gate
    assert "PHASE7_SKIP_BUILD=1" in gate
    assert 'PHASE7_IMAGE="$PHASE7_IMAGE"' not in gate
    assert 'bash "$PHASE7_SCRIPT_DIR/cluster_up.sh"' in gate


def test_phase7_release_gate_runs_full_repository_test_suite() -> None:
    gate = release_gate()

    assert "python -m pytest -q" in gate
    assert "python -m pytest tests/deployment -q" not in gate
