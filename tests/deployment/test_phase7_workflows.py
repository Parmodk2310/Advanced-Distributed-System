import re
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

    checkout = text.index(
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    )
    fetch_depth = text.index("fetch-depth: 0")
    gitleaks = text.index(
        "gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7"
    )

    assert checkout < fetch_depth < gitleaks


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


def test_phase7_heavy_verification_runs_in_main_pr_path() -> None:
    image = read(".github/workflows/phase7-image-publish.yml")
    local = read(".github/workflows/phase7-local-kubernetes.yml")

    for workflow in (image, local):
        assert "pull_request:" in workflow
        assert "branches: [main]" in workflow
        assert "pull_request_target" not in workflow

    assert "verify-image-security:" in image
    assert "Secret scan" in image
    assert "Vulnerability scan" in image
    assert "Live kind verification of exact image" in image


def test_image_workflow_tracks_inputs_and_requires_explicit_manual_publish() -> None:
    t = read(".github/workflows/phase7-image-publish.yml")

    assert "requirements-dev.txt" in t
    assert ".github/policies/**" in t
    assert "inputs.publish" in t
    assert "github.event_name == 'workflow_dispatch'" in t
    assert "github.ref == 'refs/heads/main'" in t


def test_image_pr_verification_is_read_only_and_publish_is_separate() -> None:
    text = read(".github/workflows/phase7-image-publish.yml")

    verify = text.index("  verify-image-security:")
    publish = text.index(
        "  publish:\n    name: Publish signed immutable image"
    )

    assert verify < publish
    assert "permissions:\n  contents: read" in text
    assert "needs: verify-image-security" in text[publish:]
    assert "packages: write" in text[publish:]
    assert "id-token: write" in text[publish:]
    assert "Package exact verified image for publication" in text[verify:publish]
    assert "Load and verify exact image identity" in text[publish:]


def test_all_github_actions_are_pinned_to_full_commit_shas() -> None:
    workflows = ROOT / ".github" / "workflows"
    action_ref = re.compile(r"\buses:\s+([^\s#]+)")
    immutable = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")

    for workflow in workflows.glob("*.yml"):
        for line_number, line in enumerate(workflow.read_text().splitlines(), start=1):
            match = action_ref.search(line)
            if match is None:
                continue

            target = match.group(1)
            if target.startswith("./"):
                continue

            message = (
                f"{workflow.relative_to(ROOT)}:{line_number} "
                f"uses mutable action {target}"
            )
            assert immutable.fullmatch(target), message


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

    setup_python = workflow.index(
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
    )
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


def test_public_endpoint_readiness_is_bounded_and_configurable() -> None:
    workflow = read(".github/workflows/phase7-aws-deploy.yml")

    invocation = "PYTHONPATH=src python scripts/phase7/verify_public_endpoint.py " '--host "$host"'
    assert invocation in workflow
    assert "--readiness-timeout 300" in workflow
    assert "--poll-interval 5" in workflow


def test_destroy_waits_for_ebs_convergence_before_terraform_destroy() -> None:
    workflow = read(".github/workflows/phase7-aws-deploy.yml")

    wait = workflow.index("bash scripts/phase7/wait_for_ebs_deletion.sh")
    destroy = workflow.index(
        "terraform -chdir=deploy/terraform/aws destroy " "-input=false -auto-approve"
    )

    assert wait < destroy


def test_destroy_keeps_safe_fallback_and_never_directly_deletes_ebs() -> None:
    workflow = read(".github/workflows/phase7-aws-deploy.yml")

    assert 'if [[ "$KUBERNETES_ACCESS_READY" == "true" ]]' in workflow
    assert "Kubernetes API unavailable; continuing directly to Terraform destroy" in workflow
    assert "aws ec2 delete-volume" not in workflow
