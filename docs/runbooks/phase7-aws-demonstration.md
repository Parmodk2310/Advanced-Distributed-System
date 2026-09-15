# Phase 7 temporary AWS demonstration runbook

**Status: PENDING SEPARATE APPROVAL. Do not apply Terraform from this runbook.**

The approved target is `ap-south-1`, two public worker subnets, no NAT Gateway, and one on-demand `t3.medium` worker with min/desired/max `1/1/2`. This is a temporary cost-controlled portfolio topology, not a production private-node design. The spending ceiling is USD 15 and the intended same-day demonstration is below USD 10–15.

Before approval, validate Terraform locally with `enable_eks=false`, configure a budget email, set mandatory owner/expiry tags, restrict the Kubernetes API to your current public `/32`, and save the exact `terraform plan`, checksum, resource inventory, and cost estimate. GitHub authenticates to AWS with OIDC; never create long-lived access keys.

After a separately approved apply, copy the already verified GHCR digest to ECR without rebuilding it and verify digest equivalence. Deploy that digest with Helm. Verify through `kubectl port-forward` first. Only then create a temporary LoadBalancer, capture sanitized evidence, and remove it immediately.

Destroy the cluster the same day, run `scripts/phase7/verify_aws_teardown.sh`, and inspect EKS, node groups, load balancers, NAT Gateways, EBS volumes, Elastic IPs, ECR, and tagged leftovers. Any NAT Gateway or unexpected billable resource is a failure.
