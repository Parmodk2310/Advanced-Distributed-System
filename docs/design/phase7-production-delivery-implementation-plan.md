# Phase 7 Production Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and verify Phase 7A local Kubernetes delivery and safe Phase 7B AWS EKS planning without creating AWS resources.

**Architecture:** Build one hardened node image, deploy three durable nodes through a Helm-owned StatefulSet on kind, and validate the release with deployment tests and GitHub Actions. Terraform owns only AWS infrastructure; Helm owns Kubernetes application resources. AWS apply remains inert and separately approved.

**Tech Stack:** Python 3.12, Docker/BuildKit, kind, Kubernetes, Helm 3, Bash, pytest, Terraform 1.7+, AWS provider 5.x, GitHub Actions, Trivy, Gitleaks, Checkov, kubeconform, Conftest/OPA.

**Spec:** `docs/design/phase7-production-delivery.md`

## Global Constraints

- Phase 7A may not create, modify, or delete AWS resources.
- Region is `ap-south-1`; the Phase 7B demonstration target is below USD 10–15.
- The immutable `v0.6.0` tag must not move or be rewritten.
- The repository remains private; do not create a release or merge another branch.
- Existing Phase 1–6 runtime behavior and non-guarantees remain unchanged.
- Release-mode workloads must use an image digest, never only a mutable tag.
- GHCR is the canonical registry; ECR receives the approved GHCR artifact without rebuilding it.
- `kind` is the required local and CI runtime; `k3d` is optional and must use the same chart and smoke contract.
- The AWS demonstration profile uses public worker-node networking, no NAT Gateway, and one on-demand `t3.medium` managed node with desired/minimum/maximum sizes `1/1/2`.
- EKS verification must pass through `kubectl port-forward` before creating a temporary AWS Load Balancer.
- Long-lived AWS access keys, generated private keys, Terraform state, kubeconfig, and sensitive plan files must never enter Git.
- GitHub-to-AWS authentication uses OIDC and least-privilege roles.
- Terraform owns AWS infrastructure; Helm owns Kubernetes application resources.
- Phase 7 remains “not implemented” until all applicable verification gates pass.
- `terraform apply` and EKS creation require a separate user approval of the exact plan and cost boundary.
- Every cluster-creating script and workflow must execute cleanup from a shell trap.
- CI changes must preserve the existing Python 3.12 quality gate.

---

## File ownership map

| Area | Files | Responsibility |
|---|---|---|
| Container | `Dockerfile`, `.dockerignore` | Reproducible non-root runtime image |
| Helm | `deploy/helm/distributed-system/**` | Application resources and release validation |
| Local Kubernetes | `deploy/kind/cluster.yaml`, `deploy/k3d/cluster.yaml` | Required kind gate and optional k3d parity path |
| Local orchestration | `scripts/phase7/*.sh` | Certificates, build/load, install, verify, cleanup |
| Deployment tests | `tests/deployment/**` | Static contracts and live-cluster assertions |
| Terraform | `deploy/terraform/aws/**` | Cost-bounded ECR/EKS/VPC/IAM infrastructure |
| CI/CD | `.github/workflows/phase7-*.yml`, `.github/workflows/ci.yml` | Quality, GHCR publication, local delivery, AWS plan, gated promotion/apply/destroy |
| Documentation | `docs/runbooks/**`, `docs/verification/phase7.md`, README/roadmap/architecture pages | Operations, evidence, and honest status |

### Task 1: Hardened immutable node image

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `tests/deployment/test_container_contract.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `pyproject.toml`, `src/distsys/**`, entry point `python -m distsys.main`
- Produces: OCI image `distsys-node:<commit>` running as UID/GID 10001 with writable `/data` and `/tmp`

- [ ] **Step 1: Add failing container contract tests**

Create pytest checks that require a pinned Python 3.12 slim digest, two build stages, `USER 10001:10001`, `ENTRYPOINT ["python", "-m", "distsys.main"]`, exposed ports 8000/9100, and exclusions for `.git`, virtual environments, certificates, databases, Terraform state, and test artifacts.

- [ ] **Step 2: Confirm the contract fails before implementation**

Run: `python -m pytest tests/deployment/test_container_contract.py -q`

Expected: FAIL because root `Dockerfile` and `.dockerignore` do not exist.

- [ ] **Step 3: Implement the image**

Use a wheel-builder stage and a runtime stage. Copy only the built wheel into the runtime image, create UID/GID 10001, create `/data`, install the wheel without cache, and run the existing module entry point. Do not copy certificates, source-control metadata, test directories, or local data.

- [ ] **Step 4: Build and inspect**

Run:

```bash
docker build --pull -t distsys-node:phase7-local .
docker inspect distsys-node:phase7-local   --format '{{.Config.User}} {{json .Config.Entrypoint}}'
docker run --rm --entrypoint python distsys-node:phase7-local   -c 'import distsys; print("import-ok")'
python -m pytest tests/deployment/test_container_contract.py -q
```

Expected: image builds; inspection prints UID/GID 10001 and the Python module entry point; import succeeds; tests pass.

- [ ] **Step 5: Add Make targets and commit**

Add `phase7-image` and `phase7-image-inspect` targets, then commit:

```bash
git add Dockerfile .dockerignore Makefile tests/deployment/test_container_contract.py
git commit -m "feat(phase7): add hardened node image"
```

### Task 2: Helm release contract

**Files:**
- Create: `deploy/helm/distributed-system/Chart.yaml`
- Create: `deploy/helm/distributed-system/values.yaml`
- Create: `deploy/helm/distributed-system/values-kind.yaml`
- Create: `deploy/helm/distributed-system/values-eks.yaml`
- Create: `deploy/helm/distributed-system/values-observability.yaml`
- Create: `deploy/helm/distributed-system/values.schema.json`
- Create: `deploy/helm/distributed-system/templates/_helpers.tpl`
- Create: `deploy/helm/distributed-system/templates/configmap.yaml`
- Create: `deploy/helm/distributed-system/templates/serviceaccount.yaml`
- Create: `deploy/helm/distributed-system/templates/services.yaml`
- Create: `deploy/helm/distributed-system/templates/statefulset.yaml`
- Create: `deploy/helm/distributed-system/templates/pdb.yaml`
- Create: `deploy/helm/distributed-system/templates/networkpolicy.yaml`
- Create: `deploy/helm/distributed-system/templates/NOTES.txt`
- Create: `tests/deployment/test_helm_contract.py`

**Interfaces:**
- Consumes: image repository, tag/digest, TLS Secret name, etcd endpoints, node configuration
- Produces: three-replica StatefulSet `distributed-system`, headless Service, metrics Service, ConfigMap, ServiceAccount/RBAC, PDB, and NetworkPolicies

- [ ] **Step 1: Write failing chart contract tests**

Tests must render both kind and EKS profiles and assert: three replicas; `OnDelete` or controlled `RollingUpdate` behavior selected explicitly; per-pod PVC; headless DNS; distinct protocol and metrics ports; startup/readiness/liveness probes; non-root security context; dropped capabilities; RuntimeDefault seccomp; resource requests/limits; termination grace period; default-deny ingress/egress plus explicit DNS, peer, etcd, metrics, and OTLP rules.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/deployment/test_helm_contract.py -q`

Expected: FAIL because the chart does not exist.

- [ ] **Step 3: Implement chart metadata, schema, and values**

Set chart version `0.7.0`, application version `0.6.0`, safe disabled cloud exposure, replicas `3`, replication factor `3`, conservative kind requests of 100m CPU/192Mi memory and limits of 500m/512Mi. Require a digest when `releaseMode=true`.

- [ ] **Step 4: Implement Kubernetes templates**

Derive `NODE_ID` and database path from pod hostname in the container command wrapper without altering Python behavior. Use stable seeds `distributed-system-0..2.<headless-service>`. Mount `/data`, `/tmp`, and TLS files explicitly. Keep ClusterIP services internal.

- [ ] **Step 5: Validate rendering**

Run:

```bash
helm lint deploy/helm/distributed-system   -f deploy/helm/distributed-system/values-kind.yaml
helm template phase7 deploy/helm/distributed-system   -f deploy/helm/distributed-system/values-kind.yaml   --set image.repository=distsys-node   --set image.tag=phase7-local   > /tmp/phase7-rendered.yaml
python -m pytest tests/deployment/test_helm_contract.py -q
```

Expected: lint, rendering, and contract tests pass; no Secret resource contains private-key data.

- [ ] **Step 6: Commit**

```bash
git add deploy/helm tests/deployment/test_helm_contract.py
git commit -m "feat(phase7): add Helm release contract"
```

### Task 3: Reproducible kind cluster, optional k3d parity, and ephemeral mTLS

**Files:**
- Create: `deploy/kind/cluster.yaml`
- Create: `deploy/k3d/cluster.yaml`
- Create: `scripts/phase7/common.sh`
- Create: `scripts/phase7/generate_tls_secret.sh`
- Create: `scripts/phase7/cluster_up.sh`
- Create: `scripts/phase7/cluster_down.sh`
- Create: `scripts/phase7/k3d_verify.sh`
- Create: `tests/deployment/test_phase7_scripts.py`
- Modify: `.gitignore`
- Modify: `Makefile`

**Interfaces:**
- Produces: required kind cluster `distsys-phase7`, optional k3d cluster `distsys-phase7-k3d`, namespace `distsys`, Secret `distsys-node-tls`, and the same loaded local image
- Safety: all temporary material lives below `.phase7/`; `cluster_up.sh` registers `cluster_down.sh` with `trap`

- [ ] **Step 1: Write failing script safety tests**

Assert strict shell mode, fixed cluster/namespace defaults, cleanup trap, refusal to accept a broad or empty work directory, restrictive certificate permissions, no secret output, no `kubectl create secret --dry-run ... > tracked/path` behavior, and identical Helm values/smoke entry points for kind and k3d.

- [ ] **Step 2: Confirm failure**

Run: `python -m pytest tests/deployment/test_phase7_scripts.py -q`

Expected: FAIL because scripts and kind configuration are absent.

- [ ] **Step 3: Implement kind and common safety helpers**

Use one kind control-plane node, disable default ingress, and retain kind's default storage provisioner. Define a one-server k3d profile that loads the same image and invokes the same Helm chart and verifier; keep it optional and outside the required CI gate. In `common.sh`, resolve the repository root, validate `.phase7` as the only generated workspace, and centralize tool/version checks.

- [ ] **Step 4: Implement ephemeral certificates**

Reuse `scripts/generate_dev_certs.sh` behavior where possible but generate DNS SANs for all StatefulSet identities. Apply the Secret directly from process output, never a persisted YAML file. Set private files to mode 0600 and delete them during cleanup.

- [ ] **Step 5: Implement cluster lifecycle**

Build the image, create kind, load the image, create the namespace, install etcd and the chart, and wait for readiness. On any failure, print sanitized diagnostics and run cleanup.

- [ ] **Step 6: Verify safety and lifecycle**

Run:

```bash
python -m pytest tests/deployment/test_phase7_scripts.py -q
make phase7-local-up
kubectl -n distsys get pods,pvc,svc
make phase7-local-down
kind get clusters
test ! -d .phase7/tls
scripts/phase7/k3d_verify.sh
```

Expected: kind produces three ready node pods, per-node PVCs, internal Services, no remaining `distsys-phase7` cluster, and no TLS workspace. When k3d is installed, the optional parity script runs the same chart and smoke contract and removes `distsys-phase7-k3d`; when absent, it exits with a documented skip code without weakening the kind gate.

- [ ] **Step 7: Commit**

```bash
git add deploy/kind deploy/k3d scripts/phase7 .gitignore Makefile tests/deployment/test_phase7_scripts.py
git commit -m "feat(phase7): add safe kind lifecycle"
```

### Task 4: Live deployment, persistence, and rollback verification

**Files:**
- Create: `scripts/phase7/verify_cluster.py`
- Create: `scripts/phase7/verify_persistence.py`
- Create: `scripts/phase7/verify_rollback.sh`
- Create: `tests/deployment/test_phase7_verifiers.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: namespace, release name, protocol port, CA/client identity from temporary workspace
- Produces: sanitized JSON result with commit, image ID/digest, chart version, node readiness, membership, CRDT convergence, persistence restart, and rollback status

- [ ] **Step 1: Write failing verifier unit tests**

Mock subprocess and client boundaries. Test command timeouts, JSON schema, secret redaction, non-zero exit on partial readiness, persistence mismatch, untrusted TLS acceptance, rollout failure, or rollback failure.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/deployment/test_phase7_verifiers.py -q`

Expected: FAIL because verifier modules do not exist.

- [ ] **Step 3: Implement cluster verifier**

Check all three pods and endpoints, etcd membership records, trusted mTLS operation, explicit untrusted-certificate rejection, CRDT update/read convergence, Prometheus target readiness when observability is enabled, and an OTLP trace round trip.

- [ ] **Step 4: Implement persistence verifier**

Write a unique CRDT value, record the responsible pod and PVC, delete that pod, wait through false-to-true readiness, and confirm the value and causal behavior after restart.

- [ ] **Step 5: Implement rollback verifier**

Install chart revision A, upgrade to a deliberately unhealthy but non-destructive revision B using an invalid readiness configuration, assert rollout failure, run `helm rollback --wait`, and re-run the healthy verifier. Do not introduce a database schema change.

- [ ] **Step 6: Run live gates**

Run:

```bash
make phase7-local-up
make phase7-local-verify
make phase7-persistence-verify
make phase7-rollback-verify
make phase7-local-down
```

Expected: every verifier exits zero, rollback returns to the verified revision, and cleanup removes the cluster.

- [ ] **Step 7: Commit**

```bash
git add scripts/phase7 Makefile tests/deployment/test_phase7_verifiers.py
git commit -m "test(phase7): verify Kubernetes delivery and rollback"
```

### Task 5: GitHub Actions local Kubernetes and supply-chain gates

**Files:**
- Create: `.github/workflows/phase7-local-kubernetes.yml`
- Create: `.github/workflows/phase7-image-publish.yml`
- Create: `.github/policies/kubernetes.rego`
- Create: `tests/deployment/test_phase7_workflows.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: read-only PR checks, sanitized evidence artifacts, and a GHCR image identified by SHA-256 digest after protected-branch success
- Permissions: local gate uses `contents: read`; the publication job alone receives `packages: write` and never receives AWS credentials

- [ ] **Step 1: Write failing workflow contract tests**

Parse YAML with PyYAML and assert pinned action versions, least privilege, timeouts, concurrency, BuildKit cache, Gitleaks, Trivy, SBOM generation, provenance, Helm lint/template, kubeconform, Conftest, kind lifecycle, smoke tests, and unconditional cleanup. Require GHCR publication only after all image and local gates pass, record the source commit and manifest digest, and reject `pull_request_target`, static AWS keys, unbounded artifact retention, skipped security exit codes, or mutable-tag-only deployment.

- [ ] **Step 2: Confirm failure**

Run: `python -m pytest tests/deployment/test_phase7_workflows.py -q`

Expected: FAIL because the Phase 7 workflow and policy do not exist.

- [ ] **Step 3: Implement static and supply-chain jobs**

Keep existing Python quality unchanged. Add focused jobs for filesystem secrets, dependency/image vulnerabilities, SBOM, provenance, Helm/schema/policy validation, and Terraform static checks. Use immutable tool versions or pinned actions and block Critical/High findings.

- [ ] **Step 4: Implement kind integration and GHCR publication jobs**

Build once, load the exact image ID into kind, install the chart, run Task 4 gates, upload only sanitized JSON evidence, and always delete the cluster and `.phase7`. After protected-branch success, publish that verified manifest to `ghcr.io/<owner>/advanced-distributed-system`, emit its SHA-256 digest, attach the SBOM and provenance, and sign with keyless GitHub OIDC when supported. Never rebuild between local verification and publication.

- [ ] **Step 5: Validate workflow contracts**

Run:

```bash
python -m pytest tests/deployment/test_phase7_workflows.py -q
python -m pytest -q
python -m ruff check src tests scripts
python -m black --check src tests scripts
python -m mypy src/distsys
```

Expected: all checks pass.

- [ ] **Step 6: Commit**

```bash
git add .github Makefile tests/deployment/test_phase7_workflows.py
git commit -m "ci(phase7): add Kubernetes and supply-chain gates"
```

### Task 6: Cost-bounded AWS Terraform foundation

**Files:**
- Create: `deploy/terraform/aws/versions.tf`
- Create: `deploy/terraform/aws/providers.tf`
- Create: `deploy/terraform/aws/variables.tf`
- Create: `deploy/terraform/aws/locals.tf`
- Create: `deploy/terraform/aws/network.tf`
- Create: `deploy/terraform/aws/ecr.tf`
- Create: `deploy/terraform/aws/eks.tf`
- Create: `deploy/terraform/aws/iam.tf`
- Create: `deploy/terraform/aws/budget.tf`
- Create: `deploy/terraform/aws/outputs.tf`
- Create: `deploy/terraform/aws/terraform.tfvars.example`
- Create: `deploy/terraform/aws/backend.hcl.example`
- Create: `deploy/terraform/aws/README.md`
- Create: `tests/deployment/test_terraform_contract.py`
- Modify: `.gitignore`

**Interfaces:**
- Terraform version: `>= 1.7.0`
- AWS provider: `~> 5.0`
- Inputs include `aws_region`, `project_name`, `environment`, `monthly_budget_usd`, `enable_eks`, node capacity, and mandatory owner/expiry tags
- Safe default: `enable_eks=false`

- [ ] **Step 1: Write failing Terraform contract tests**

Assert disabled-by-default EKS, `ap-south-1` example, budget threshold, mandatory tags, two public subnets, no NAT Gateway, no unrestricted Kubernetes API CIDR, encrypted EBS, private ECR scanning, ECR lifecycle, least-privilege IAM, OIDC inputs, one on-demand `t3.medium` managed node by default, node sizes `1/1/2`, and no Helm/Kubernetes provider resources.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/deployment/test_terraform_contract.py -q`

Expected: FAIL because Terraform files do not exist.

- [ ] **Step 3: Implement versions, providers, variables, tags, and budget**

Use remote-state-ready configuration, provider default tags, validation for budget/region/CIDRs, and a budget alert below the USD 15 ceiling. Do not embed account IDs, emails, credentials, or generated backend names.

- [ ] **Step 4: Implement low-cost network, ECR, EKS, and IAM**

Use two public subnets across two availability zones, explicit routing through an Internet Gateway, no NAT Gateway, one on-demand `t3.medium` managed node group with minimum/desired/maximum values `1/1/2`, encrypted storage, restricted control-plane CIDRs, restrictive node security groups, and IRSA-ready roles. Document this as a temporary cost-controlled profile rather than a production private-node topology. Ensure `enable_eks=false` yields no EKS/node-group resources.

- [ ] **Step 5: Validate without AWS access**

Run:

```bash
terraform -chdir=deploy/terraform/aws fmt -check -recursive
terraform -chdir=deploy/terraform/aws init -backend=false
terraform -chdir=deploy/terraform/aws validate
checkov -d deploy/terraform/aws
python -m pytest tests/deployment/test_terraform_contract.py -q
```

Expected: all static gates pass; no AWS API mutation occurs.

- [ ] **Step 6: Commit the provider lock file and module**

Review `.terraform.lock.hcl`, commit it, and never commit `.terraform/`, state, plan binaries, or generated kubeconfig.

```bash
git add deploy/terraform/aws .gitignore tests/deployment/test_terraform_contract.py
git commit -m "feat(phase7): add cost-bounded EKS infrastructure"
```

### Task 7: Inert AWS plan and separately gated deployment workflows

**Files:**
- Create: `.github/workflows/phase7-aws-plan.yml`
- Create: `.github/workflows/phase7-aws-deploy.yml`
- Create: `scripts/phase7/promote_ghcr_to_ecr.sh`
- Create: `scripts/phase7/verify_eks.sh`
- Create: `scripts/phase7/enable_public_endpoint.sh`
- Create: `scripts/phase7/disable_public_endpoint.sh`
- Create: `scripts/phase7/verify_aws_teardown.sh`
- Modify: `tests/deployment/test_phase7_workflows.py`

**Interfaces:**
- GitHub variables: `AWS_PHASE7_ENABLED` defaults absent/false, `AWS_REGION=ap-south-1`, `AWS_ROLE_ARN`
- Protected environment: `phase7-aws-demo`
- Deployment inputs: exact plan artifact ID, expected commit SHA, approved GHCR digest, and `action=apply|verify|destroy`

- [ ] **Step 1: Extend failing workflow tests**

Require manual dispatch, OIDC `id-token: write` only in AWS jobs, explicit false-by-default gate, protected environment, exact plan/commit/GHCR-digest binding, no `apply -auto-approve` outside the gated job, digest-preserving ECR promotion, port-forward verification before public exposure, temporary load-balancer deletion, guaranteed destroy path, and tagged-resource teardown verification.

- [ ] **Step 2: Confirm failure**

Run: `python -m pytest tests/deployment/test_phase7_workflows.py -q`

Expected: FAIL because AWS workflows are absent.

- [ ] **Step 3: Implement plan workflow**

Authenticate through OIDC, run read-only account identity and Terraform plan with `enable_eks=true`, produce human-readable resource/cost inventory, encrypt or safely retain the binary plan for a short period, and expose no secret values. The workflow must stop when `AWS_PHASE7_ENABLED != 'true'`.

- [ ] **Step 4: Implement deploy workflow**

Require manual action, protected-environment approval, exact source commit, exact saved plan, exact approved GHCR digest, and a second enablement check. Apply only the reviewed plan. Copy the approved OCI manifest from GHCR to ECR without rebuilding it, resolve both registry digests, and fail unless manifest equivalence is proven. Deploy the ECR digest through Helm, verify first through `kubectl port-forward`, then create the temporary AWS Load Balancer, run health/routing/observability/scaling/rollback checks, capture sanitized evidence, and delete the load balancer. The destroy action must generate and apply a destroy plan, then call the teardown verifier.

- [ ] **Step 5: Implement teardown verification**

Query region-scoped resources by the mandatory Phase 7 tags and explicitly check EKS clusters/node groups, load balancers, NAT Gateways, EBS volumes, Elastic IPs, ECR policy expectations, and CloudFormation leftovers. Treat an unexpected NAT Gateway as a contract violation. Exit non-zero with resource identifiers when any unexpected billable resource remains.

- [ ] **Step 6: Validate statically only**

Run:

```bash
python -m pytest tests/deployment/test_phase7_workflows.py -q
bash -n scripts/phase7/promote_ghcr_to_ecr.sh
bash -n scripts/phase7/enable_public_endpoint.sh
bash -n scripts/phase7/disable_public_endpoint.sh
bash -n scripts/phase7/verify_aws_teardown.sh
```

Expected: PASS. Do not dispatch either AWS workflow during Phase 7A.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/phase7-aws-plan.yml .github/workflows/phase7-aws-deploy.yml scripts/phase7/promote_ghcr_to_ecr.sh scripts/phase7/verify_eks.sh scripts/phase7/enable_public_endpoint.sh scripts/phase7/disable_public_endpoint.sh scripts/phase7/verify_aws_teardown.sh tests/deployment/test_phase7_workflows.py
git commit -m "ci(phase7): gate AWS plan deployment and teardown"
```

### Task 8: Runbooks, architecture status, and evidence template

**Files:**
- Create: `docs/runbooks/phase7-local-kubernetes.md`
- Create: `docs/runbooks/phase7-aws-demonstration.md`
- Create: `docs/runbooks/phase7-rollback.md`
- Create: `docs/runbooks/phase7-security-and-secrets.md`
- Create: `docs/verification/phase7.md`
- Modify: `docs/architecture/phase7-production-delivery.md`
- Modify: `docs/architecture/README.md`
- Modify: `docs/roadmap.md`
- Modify: `README.md`
- Create: `tests/deployment/test_phase7_documentation.py`

**Interfaces:**
- Status after Phase 7A: “Local Kubernetes delivery implemented and verified; AWS EKS demonstration pending”
- Status after Phase 7B only: “Temporary AWS EKS deployment verified and destroyed”

- [ ] **Step 1: Write failing documentation contract tests**

Validate relative links, exact status language, required teardown warnings, non-guarantees, kind and optional k3d commands, GHCR-to-ECR provenance, cost ceiling, no-NAT public-node limitation, private-first verification, temporary-load-balancer removal, AWS approval gate, recovery/rollback limitations, and absence of completion claims without evidence fields.

- [ ] **Step 2: Confirm failure**

Run: `python -m pytest tests/deployment/test_phase7_documentation.py -q`

Expected: FAIL because runbooks and verification record are absent.

- [ ] **Step 3: Write operational runbooks**

Document prerequisites, pinned tool versions, required kind lifecycle, optional k3d parity, troubleshooting, rollback, certificate rotation, GHCR publication, digest-preserving ECR promotion, OIDC, Terraform plan review, cost inventory, the public-node security trade-off, port-forward-first verification, temporary load-balancer lifecycle, apply authorization, evidence capture, destroy, and zero-resource verification. Never include real account IDs, role ARNs, credentials, certificate contents, or personal email addresses.

- [ ] **Step 4: Create the verification record**

Record commands and expected evidence fields. Populate only results actually observed. For Phase 7B, retain an explicit `PENDING SEPARATE APPROVAL` status rather than fabricated output.

- [ ] **Step 5: Update public-facing status after gates pass**

After Tasks 1–7 and live local verification pass, change Phase 7 status to local implementation complete with AWS pending. Keep all non-guarantees visible and preserve the Phase 6 verification checkpoint.

- [ ] **Step 6: Validate documentation**

Run: `python -m pytest tests/deployment/test_phase7_documentation.py -q`

Expected: PASS with every relative link resolved.

- [ ] **Step 7: Commit**

```bash
git add README.md docs tests/deployment/test_phase7_documentation.py
git commit -m "docs(phase7): publish delivery runbooks and evidence"
```

### Task 9: Cumulative Phase 7A release gate

**Files:**
- Create: `scripts/phase7/release_gate.sh`
- Modify: `Makefile`
- Modify: `docs/verification/phase7.md`

**Interfaces:**
- Produces: sanitized `.phase7/evidence/phase7-local-verification.json`
- Exit code: zero only when every static and live local gate passes and cleanup succeeds

- [ ] **Step 1: Implement fail-closed orchestration**

Use strict shell mode and an EXIT trap. Run Python quality, container contracts/build/inspection, Helm/schema/policy validation, Terraform static validation, workflow/documentation contracts, required kind deployment, optional k3d parity when installed, mTLS rejection, CRDT convergence, persistence restart, observability, rollout, rollback, and cleanup.

- [ ] **Step 2: Run focused static suite**

Run:

```bash
python -m pytest tests/deployment -q
terraform -chdir=deploy/terraform/aws fmt -check -recursive
terraform -chdir=deploy/terraform/aws init -backend=false
terraform -chdir=deploy/terraform/aws validate
helm lint deploy/helm/distributed-system   -f deploy/helm/distributed-system/values-kind.yaml
```

Expected: all commands pass without AWS resource creation.

- [ ] **Step 3: Run the complete repository quality gate**

Run:

```bash
python -m compileall -q src scripts tests
make quality
```

Expected: all existing and new tests pass; Ruff, Black, and mypy pass.

- [ ] **Step 4: Run the local Phase 7 release gate**

Run: `make phase7-release-gate`

Expected: three-node local Kubernetes verification passes, rollback succeeds, evidence is sanitized, and kind/TLS cleanup succeeds.

- [ ] **Step 5: Inspect scope and secrets**

Run:

```bash
git status --short
git diff --check
git grep -nE 'AKIA[0-9A-Z]{16}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY'
git tag --points-at v0.6.0
```

Expected: no credentials/private keys, no unexpected generated files, and no tag mutation.

- [ ] **Step 6: Commit final Phase 7A evidence**

```bash
git add Makefile scripts/phase7/release_gate.sh docs/verification/phase7.md
git commit -m "chore(phase7): complete local delivery verification"
```

- [ ] **Step 7: Verify GitHub Actions**

Push the tested commit to `main`, wait for Quality and Phase 7 Local Kubernetes workflows to reach terminal success, and record their run URLs in `docs/verification/phase7.md`. If either fails, diagnose and fix it before claiming Phase 7A complete.

## Phase 7B handoff gate

Stop after Phase 7A. Present the following to the user in one review:

- exact source commit;
- canonical GHCR image digest and provenance/SBOM references;
- proposed ECR repository and digest-equivalence procedure;
- chart version;
- Terraform plan summary and plan checksum;
- full AWS resource inventory;
- estimated hourly and same-day cost;
- budget alert configuration;
- public endpoint and IPv4/NAT/load-balancer costs;
- confirmation that the reviewed plan contains no NAT Gateway;
- port-forward verification procedure and temporary load-balancer lifetime;
- deployment duration;
- teardown commands and verification checks.

Only an explicit approval of that exact package authorizes Phase 7B `terraform apply`. Approval of this plan does not authorize AWS creation.
