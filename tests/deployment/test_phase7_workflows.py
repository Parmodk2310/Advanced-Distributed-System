from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"


def load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def test_local_workflow_is_bounded_and_cleans_up() -> None:
    text = (WORKFLOWS / "phase7-local-kubernetes.yml").read_text()
    workflow = load("phase7-local-kubernetes.yml")
    assert workflow["permissions"] == {"contents": "read"}
    assert "timeout-minutes" in text and "concurrency" in text
    assert "release_gate.sh" in text
    assert "if: always()" in text and "cluster_down.sh" in text
    assert "retention-days: 7" in text
    assert "pull_request_target" not in text


def test_image_workflow_enforces_supply_chain_controls() -> None:
    text = (WORKFLOWS / "phase7-image-publish.yml").read_text()
    workflow = load("phase7-image-publish.yml")
    assert workflow["permissions"] == {
        "attestations": "write",
        "contents": "read",
        "id-token": "write",
        "packages": "write",
    }
    assert "gitleaks/gitleaks-action" in text
    assert "aquasecurity/trivy-action" in text
    assert "anchore/sbom-action" in text
    assert "actions/attest-build-provenance" in text
    assert "github.event.repository.visibility == 'public'" in text
    assert "provenance.json" in text
    assert "ghcr.io/parmodk2310/distsys-node" in text
    assert "kubeconform" in text and "conftest" in text


def test_local_workflow_validates_terraform_without_applying() -> None:
    text = (WORKFLOWS / "phase7-local-kubernetes.yml").read_text()
    assert "terraform-static" in text
    assert "terraform fmt -check -recursive" in text
    assert "terraform init -backend=false" in text
    assert "terraform validate" in text
    assert "terraform apply" not in text


def test_aws_workflows_are_manual_oidc_and_disabled_by_default() -> None:
    text = "\n".join(
        (WORKFLOWS / name).read_text() for name in ("phase7-aws-plan.yml", "phase7-aws-deploy.yml")
    )
    assert "workflow_dispatch" in text
    assert "id-token: write" in text
    assert "AWS_PHASE7_ENABLED == 'true'" in text
    assert "environment: phase7-aws-demo" in text
    assert "approved_ghcr_digest" in text and "expected_commit" in text
    assert "AKIA" not in text
