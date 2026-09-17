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


def test_aws_deploy_uses_temporary_runner_api_access() -> None:
    text = read(".github/workflows/phase7-aws-deploy.yml")

    assert "- name: Temporarily authorize GitHub runner for EKS API" in text
    assert "id: eks_api_access" in text
    assert "CHECK_IP_HOST: checkip.amazonaws.com" in text
    assert '"https://${CHECK_IP_HOST}"' in text
    assert 'runner_cidr="${runner_ip}/32"' in text
    assert "publicAccessCidrs" in text
    assert "aws eks update-cluster-config" in text
    assert "aws eks wait cluster-active" in text
    assert 'index("0.0.0.0/0") == null' in text


def test_aws_deploy_restores_approved_api_cidrs_even_after_failure() -> None:
    text = read(".github/workflows/phase7-aws-deploy.yml")

    assert "- name: Always restore approved EKS API CIDRs" in text
    assert "if: always()" in text
    assert "TF_VAR_kubernetes_api_cidrs" in text
    assert "Restore approved EKS API CIDRs" in text


def test_aws_deploy_does_not_treat_terraform_warnings_as_cluster_name() -> None:
    text = read(".github/workflows/phase7-aws-deploy.yml")

    assert "terraform -chdir=deploy/terraform/aws output -json" in text
    assert "jq -r '.cluster_name.value // empty'" in text
    assert "output -raw cluster_name 2>/dev/null || true" not in text


def test_aws_destroy_reaches_terraform_without_kubernetes_access() -> None:
    text = read(".github/workflows/phase7-aws-deploy.yml")

    assert "- name: Destroy application, etcd and AWS infrastructure" in text
    assert "if: always() && inputs.action == 'destroy'" in text
    assert "KUBERNETES_ACCESS_READY" in text
    assert 'if [[ "$KUBERNETES_ACCESS_READY" == "true" ]]' in text
    assert "terraform -chdir=deploy/terraform/aws destroy " "-input=false -auto-approve" in text


def test_temporary_public_endpoint_cleanup_is_idempotent() -> None:
    text = read("scripts/phase7/disable_public_endpoint.sh")

    assert 'delete service "${PHASE7_RELEASE}-public" ' "--ignore-not-found" in text
    assert (
        "delete networkpolicy "
        '"${PHASE7_RELEASE}-temporary-public-ingress" '
        "--ignore-not-found" in text
    )


def test_aws_apply_requires_cluster_output_but_destroy_can_continue() -> None:
    workflow = read(".github/workflows/phase7-aws-deploy.yml")

    assert 'if [[ "$ACTION" == "destroy" ]]' in workflow
    assert "No EKS cluster output during apply-demo" in workflow
    assert "Kubernetes cleanup will be skipped" in workflow


def test_aws_deploy_installs_python_dependencies_before_verification() -> None:
    workflow = read(".github/workflows/phase7-aws-deploy.yml")

    setup_python = workflow.index("actions/setup-python@v5")
    install_dependencies = workflow.index("python -m pip install -e .")
    private_verification = workflow.index(
        "- name: Private EKS, persistence and rollback verification"
    )

    assert setup_python < install_dependencies < private_verification


def test_aws_destroy_passes_exact_backend_allowlist_to_teardown_verifier() -> None:
    workflow = read(".github/workflows/phase7-aws-deploy.yml")

    assert "PHASE7_TF_STATE_BUCKET: ${{ vars.TF_STATE_BUCKET }}" in workflow
    assert "PHASE7_TF_LOCK_TABLE: ${{ vars.TF_LOCK_TABLE }}" in workflow
    assert "bash scripts/phase7/verify_aws_teardown.sh" in workflow
