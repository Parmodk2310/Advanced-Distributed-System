from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(p):
    return (ROOT / p).read_text()


def test_local_workflow_has_no_aws_credentials_and_runs_release_gate():
    t = read(".github/workflows/phase7-local-kubernetes.yml")
    assert "phase7/release_gate.sh" in t
    assert "aws-actions/configure-aws-credentials" not in t
    assert "pull_request_target" not in t


def test_image_workflow_scans_sbom_signs_and_publishes_digest():
    t = read(".github/workflows/phase7-image-publish.yml")
    for required in (
        "gitleaks",
        "trivy-action",
        "sbom-action",
        "cosign sign",
        "crane digest",
        "packages: write",
    ):
        assert required in t
    assert ":latest" not in t
    assert "image.tag=latest" not in t


def test_image_workflow_fetches_full_history_before_gitleaks() -> None:
    text = read(".github/workflows/phase7-image-publish.yml")

    assert """      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
""" in text


def test_aws_plan_is_manual_oidc_and_saved_plan():
    t = read(".github/workflows/phase7-aws-plan.yml")
    assert "workflow_dispatch" in t
    assert "id-token: write" in t
    assert "configure-aws-credentials" in t
    assert "phase7.tfplan" in t and "phase7-plan.sha256" in t
    assert "AWS_ACCESS_KEY_ID" not in t and "AWS_SECRET_ACCESS_KEY" not in t


def test_aws_deploy_requires_explicit_confirmation_exact_commit_and_digest():
    t = read(".github/workflows/phase7-aws-deploy.yml")
    assert "PHASE7_EKS_APPROVED" in t
    assert "inputs.expected_commit == github.sha" in t
    assert "approved_ghcr_digest" in t
    assert "reviewed_plan_run_id" in t
    assert "promote_ghcr_to_ecr.sh" in t
    assert "phase7-etcd" in t
    assert "verify_public_endpoint.py" in t
    assert "terraform -chdir=deploy/terraform/aws destroy" in t


def test_image_workflow_uses_phase7_policy_namespace() -> None:
    text = read(".github/workflows/phase7-image-publish.yml")

    assert (
        "test --namespace phase7.kubernetes "
        "--policy /project/.github/policies "
        "/project/.phase7/rendered" in text
    )


def test_image_workflow_does_not_ignore_unfixed_high_critical_findings() -> None:
    t = read(".github/workflows/phase7-image-publish.yml")

    assert "HIGH,CRITICAL" in t
    assert 'exit-code: "1"' in t
    assert "ignore-unfixed: false" in t
    assert "ignore-unfixed: true" not in t


def test_phase7_verification_runs_on_feature_branch_pushes() -> None:
    image = read(".github/workflows/phase7-image-publish.yml")
    local = read(".github/workflows/phase7-local-kubernetes.yml")

    assert "branches: [main]" not in image
    assert "branches: [main]" not in local


def test_image_workflow_tracks_inputs_and_requires_explicit_manual_publish() -> None:
    t = read(".github/workflows/phase7-image-publish.yml")

    assert "requirements-dev.txt" in t
    assert ".github/policies/**" in t
    assert "inputs.publish" in t
    assert "github.event_name == 'workflow_dispatch'" in t
    assert "github.ref == 'refs/heads/main'" in t
