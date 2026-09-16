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
