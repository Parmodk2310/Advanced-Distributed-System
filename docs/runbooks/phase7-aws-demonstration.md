# Phase 7 temporary AWS EKS demonstration runbook

Do not run until the exact Terraform plan and spending boundary are explicitly approved.

Required GitHub protected configuration: `AWS_PHASE7_ENABLED`, `AWS_ROLE_ARN`, `TF_STATE_BUCKET`, `TF_LOCK_TABLE`, `PHASE7_OWNER`, `PHASE7_EXPIRES_AT`, `PHASE7_API_CIDRS_JSON`, and secret `PHASE7_BUDGET_EMAIL`.

Sequence:
1. Keep `AWS_PHASE7_ENABLED=false` during normal development.
2. Produce the immutable GHCR digest only after local gates pass.
3. Enable the protected environment and run **Phase 7 AWS Plan**.
4. Review the plan text, checksum, API CIDR, region, worker sizing and teardown path.
5. Explicitly approve the exact plan/digest/commit.
6. Run **Phase 7 AWS Deploy** with `apply-demo` and `PHASE7_EKS_APPROVED`.
7. Verify private cluster, persistence, rollback and temporary public endpoint evidence.
8. Run the same workflow with `destroy` immediately after evidence capture.
9. Require `aws-teardown.json` to report zero unexpected tagged resources.

The demo uses one worker by default. Three etcd members on that worker are not node/AZ-level HA.

## GitHub runner access to the EKS API

`PHASE7_API_CIDRS_JSON` is the permanent allowlist for the EKS public
API endpoint. It must contain only explicitly approved CIDRs and must
never contain `0.0.0.0/0`.

The deployment role requires `eks:UpdateClusterConfig`. During an
approved deployment or teardown, the workflow discovers the
GitHub-hosted runner IPv4 address as a /32, temporarily merges it with
`PHASE7_API_CIDRS_JSON`, and waits for the EKS configuration update
before using `kubectl` or Helm.

The workflow never makes the Kubernetes API generally public. Its
`always` cleanup path always restores the exact CIDRs supplied through
`PHASE7_API_CIDRS_JSON`. If Kubernetes access cannot be established
during teardown, Helm and PVC cleanup are skipped and Terraform
destruction continues so that EKS does not remain billable.

After every run, confirm that the cluster either no longer exists or
its `publicAccessCidrs` exactly match `PHASE7_API_CIDRS_JSON`.

## Teardown convergence

AWS may continue deleting Kubernetes-created EBS volumes after
Terraform has removed the EKS cluster. The teardown verifier therefore
polls for up to 600 seconds before reporting unexpected tagged
resources.

The permanent Terraform state bucket and lock table are retained
intentionally and are allowed only by their exact protected names.
Every other tagged resource, including EBS volumes, must disappear
before `aws-teardown.json` reports success. Because the Resource Groups
Tagging API can temporarily return deleted EBS ARNs, the verifier
ignores a volume record only after the EC2 API returns
`InvalidVolume.NotFound`. Existing volumes and other AWS errors remain
teardown failures.
