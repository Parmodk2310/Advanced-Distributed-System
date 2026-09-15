# Phase 7 — Production Delivery and AWS EKS Demonstration

## Status

**APPROVED DESIGN — NOT IMPLEMENTED**

This specification defines Phase 7. It does not claim that Kubernetes or AWS deployment has already been completed. Phase 7 becomes implemented and verified only after every mandatory local gate passes. AWS EKS remains a separately approved, temporary demonstration.

## Purpose

Phase 7 packages the Phase 1–6 distributed system as one immutable container artifact, validates it on local Kubernetes, and provides a reproducible path to a temporary AWS EKS deployment. It preserves the existing correctness, durability, security, observability, chaos, and performance boundaries while adding delivery engineering, supply-chain controls, cloud infrastructure as code, rollback, cost governance, and teardown evidence.

## Delivery boundaries

Phase 7 is divided into two explicit stages.

### Phase 7A — Local delivery and infrastructure validation

Phase 7A may be implemented without creating AWS resources. It includes:

- a production-oriented multi-stage node image;
- a laptop-safe `kind` cluster;
- a Helm release contract for three distributed-system nodes;
- local persistent storage, etcd, mTLS, health probes, metrics, and tracing;
- GitHub Actions for container, Helm, Kubernetes, Terraform, security, and policy checks;
- Terraform formatting, validation, static security analysis, and a reviewed plan;
- reproducible smoke, rollout, rollback, persistence, and cleanup evidence.

### Phase 7B — Temporary EKS demonstration

Phase 7B is outside the initial implementation authority. Before `terraform apply`, the user must approve the exact Terraform plan, expected resources, region, estimated spend, and teardown procedure.

The intended boundary is:

- region: `ap-south-1`;
- target demonstration spend: below USD 10–15;
- use available AWS credits as a ceiling, not a spending target;
- deploy for a short verification window;
- capture non-secret evidence;
- destroy the environment the same day;
- verify that no Phase 7 billable resources remain.

No AWS resource is created merely by committing this design or implementing Phase 7A.

## Architectural decisions

### Immutable artifact

CI builds one node image from a pinned Python 3.12 base image. The image:

- installs only runtime dependencies;
- runs as a non-root user;
- contains no credentials, generated certificates, mutable database, or test artifacts;
- exposes the node protocol and observability ports;
- uses the existing `distsys.main` entry point;
- receives configuration only at runtime;
- is scanned before promotion;
- is promoted by immutable digest rather than a mutable tag.

The same image digest must be used by local verification and the EKS demonstration. A rebuild is a new artifact and must repeat the gates.

GitHub Container Registry (GHCR) is the canonical registry. CI publishes the verified image to GHCR and records the source commit, SBOM, scan result, provenance, and SHA-256 digest. After the AWS approval gate, the deployment workflow copies that exact digest into Amazon ECR without rebuilding it. The ECR digest deployed to EKS must resolve to the same manifest content as the approved GHCR artifact.

### Local Kubernetes

`kind` is the required local runtime because it is compatible with Docker/WSL, appropriate for a 16-GB development laptop, and reproducible in GitHub Actions.

`k3d` is an optional developer convenience path. It uses the same Helm chart, security contract, image digest, and smoke tests as `kind`; it is not a separate deployment implementation and is not required in CI.

The default local profile uses:

- one kind control-plane container;
- three distributed-system pods;
- one etcd pod for development coordination;
- conservative resource requests and limits;
- local-path storage suitable only for development verification;
- optional observability components enabled through Helm values;
- no cloud load balancer.

### Workload identity and topology

Distributed-system nodes use a three-replica StatefulSet. Stable pod DNS names provide deterministic node identities and seed addresses. A headless Service provides peer discovery; a separate metrics Service supports scraping.

Each node receives a distinct persistent volume for SQLite. Pod identity, persistence paths, peer seeds, and observability ports are derived deterministically from the StatefulSet ordinal. Kubernetes scheduling does not replace the existing SWIM membership protocol or etcd coordination logic.

### Configuration and secrets

Non-sensitive settings use ConfigMaps or Helm values. Secret values never enter Git.

For local verification, a script generates an ephemeral development CA and per-node certificates into a temporary ignored directory, then creates Kubernetes Secrets. Generated private keys and rendered secret manifests must not be committed or uploaded as workflow artifacts.

For AWS, the target integration is AWS Secrets Manager with External Secrets Operator and IRSA. Installing or operating that integration belongs to Phase 7B. Static AWS access keys are prohibited in Kubernetes Secrets and GitHub repository variables.

### Health and lifecycle

Existing independent health endpoints remain authoritative:

- liveness: `/health/live`;
- readiness: `/health/ready`.

Readiness must remain false during persistence restore and reconciliation. A pod may receive traffic only after the existing recovery gate passes. Graceful termination must remove readiness first, allow in-flight work to drain, stop background replication and coordination loops, and then exit within the pod termination grace period.

A PodDisruptionBudget prevents an intentional voluntary disruption from removing multiple replicas simultaneously during the demonstration. It does not create quorum guarantees.

### Observability

Prometheus metrics and OpenTelemetry traces remain outside the correctness-critical path. Local validation may deploy the existing Prometheus, Grafana, Tempo, and OpenTelemetry Collector configuration through a disabled-by-default observability profile.

AWS Phase 7B must use bounded retention and avoid expensive always-on managed observability services unless the reviewed plan explicitly includes them. Evidence must show health, target discovery, a trace round trip, and a controlled rollout without exposing credentials or certificate material.

### Security

The Kubernetes release contract requires:

- non-root execution;
- read-only root filesystem where compatible with Python runtime requirements;
- dropped Linux capabilities;
- no privilege escalation;
- seccomp RuntimeDefault;
- explicit writable mounts only for SQLite and temporary runtime data;
- resource requests and limits;
- namespace-scoped RBAC with least privilege;
- default-deny NetworkPolicies with documented allowed paths;
- mTLS for node-to-node communication;
- pinned container image digests in verified releases.

CI performs secret scanning, dependency and image vulnerability scanning, Helm validation, Terraform security checks, and policy checks. Any Critical vulnerability blocks promotion. High-severity findings block by default and require a documented, time-bounded exception.

## Helm ownership boundary

Helm owns Kubernetes application resources:

- Namespace metadata where permitted;
- ServiceAccounts and namespace-scoped RBAC;
- ConfigMaps;
- Services and headless Services;
- StatefulSet;
- PodDisruptionBudget;
- NetworkPolicies;
- optional ServiceMonitor-compatible resources when enabled;
- hooks or Jobs used only for bounded verification.

Terraform must not duplicate resources owned by Helm.

The chart provides separate values for:

- `values.yaml`: safe defaults;
- `values-kind.yaml`: laptop-safe local verification;
- `values-eks.yaml`: cloud target without secrets;
- `values-observability.yaml`: optional monitoring profile.

Helm templates must fail early for invalid replica counts, missing image digests in release mode, incompatible replication factors, unsafe service exposure, and incomplete TLS configuration.

## Terraform ownership boundary

Terraform owns AWS infrastructure only:

- budget alert and cost tags;
- VPC, subnets, routing, and required endpoints;
- ECR repository and lifecycle policy;
- EKS cluster and managed node group;
- IAM roles and IRSA bindings;
- storage classes or supporting AWS resources when required;
- outputs consumed by the deployment workflow.

The low-cost design avoids a NAT Gateway unless the reviewed dependency path proves it necessary. Public/private subnet choices, VPC endpoints, load balancers, and public IPv4 addresses must appear explicitly in the cost review.

The approved demonstration profile uses a cost-controlled VPC with public worker-node networking, tightly restricted security groups, and no NAT Gateway. The default managed node group uses one on-demand `t3.medium` node with desired/minimum/maximum sizes of `1/1/2`. This is a temporary demonstration compromise, not the recommended production topology; a production deployment should normally use private worker nodes and a separately reviewed egress design.

Application verification begins without a public application endpoint and uses `kubectl port-forward`. Only after the private checks pass may the workflow create a temporary AWS Load Balancer for health, routing, observability, scaling, and rollback evidence. The load balancer must be deleted before final cluster destruction. Kubernetes API and application access must be restricted to the approved operator and workflow paths.

Terraform state must use a documented remote-state bootstrap for Phase 7B. State files, plans containing sensitive values, credentials, and kubeconfig files must never be committed.

## CI/CD gates

Existing Python quality checks remain mandatory. Phase 7 adds:

1. Dockerfile lint and deterministic image build.
2. Software bill of materials generation.
3. Secret, dependency, filesystem, and image scanning plus artifact provenance and signing when the configured identity supports it.
4. Helm lint, template rendering, schema checks, and policy validation.
5. kind cluster creation with guaranteed cleanup.
6. installation of the exact locally built image and Helm chart.
7. rollout, health, mTLS, persistence, and restart smoke tests.
8. rollback verification between two known chart revisions.
9. Terraform format, validate, documentation, and security checks.
10. publication of the verified digest to GHCR.
11. an AWS-plan workflow protected by explicit enablement and environment approval.
12. digest-preserving promotion from GHCR to ECR after approval.
13. a separate manually dispatched EKS apply/destroy workflow for Phase 7B.

CI must use least-privilege permissions. AWS authentication uses GitHub OpenID Connect and an assumable role; long-lived AWS keys are prohibited.

## Release and rollback

A release candidate is identified by source commit, image digest, chart version, and verification evidence. Tags do not bypass gates.

Rollback must:

- select a previously verified image digest and chart revision;
- use Helm rollback or an equivalent declarative reconciliation;
- wait for all readiness gates;
- confirm node membership, CRDT operation, persistence, metrics, and tracing;
- retain evidence of both the failed and recovered revisions.

Rollback does not reverse already persisted application data. Schema changes that would make rollback unsafe are outside Phase 7 unless a compatible migration strategy is separately designed.

## Test strategy and acceptance gates

### Static and unit gates

- existing Python quality suite passes;
- Dockerfile and shell scripts lint;
- Helm chart lint/template/schema tests pass;
- Kubernetes policy tests pass;
- Terraform format, validate, and static security checks pass;
- documentation links and commands validate.

### Local integration gates

- kind cluster is created reproducibly and always cleaned up;
- three nodes become ready;
- headless DNS and stable node identity work;
- etcd registration and lease expiry work;
- mTLS rejects untrusted peers;
- CRDT operations converge across nodes;
- a pod restart preserves its SQLite-backed state;
- readiness remains false through recovery;
- metrics targets are healthy and a trace reaches Tempo;
- rolling upgrade preserves availability within stated boundaries;
- rollback restores the prior verified revision;
- no generated secret or private key enters Git or artifacts.

### AWS demonstration gates

After separate approval:

- the reviewed Terraform plan matches the applied resources;
- budget and ownership tags exist before or with billable infrastructure;
- ECR promotion copies the verified GHCR digest without rebuilding and verifies manifest equivalence;
- EKS rollout passes the same Helm and smoke contracts;
- private `kubectl port-forward` verification passes before public exposure;
- a temporary AWS Load Balancer passes health and routing checks and is then removed;
- observability, restart, rollout, and rollback evidence is captured;
- `terraform destroy` succeeds;
- follow-up checks confirm no Phase 7 cluster, node group, load balancer, NAT Gateway, unattached volume, elastic IP, or other tagged billable resource remains.

## Repository layout

The implementation plan may refine filenames, but the ownership layout is fixed:

```text
Dockerfile
.dockerignore
.github/workflows/
  ci.yml
  phase7-local-kubernetes.yml
  phase7-aws-plan.yml
  phase7-aws-deploy.yml
deploy/
  helm/distributed-system/
  kind/
  k3d/
  terraform/aws/
scripts/
  phase7/
tests/
  deployment/
docs/
  design/phase7-production-delivery.md
  verification/phase7.md
  runbooks/
```

The AWS deploy workflow must be inert by default and require manual dispatch, an explicit enablement variable, a protected GitHub environment, and approval of the exact plan artifact. Its normal sequence is plan review, budget guard creation, ECR promotion, EKS creation, Helm deployment, private verification, temporary load-balancer verification, resilience and rollback checks, evidence capture, destroy, and zero-resource verification. Cleanup must still run after a failed verification step.

## Documentation and evidence

Phase 7 documentation must include:

- local setup and teardown;
- chart configuration and ownership boundaries;
- AWS cost model and deployment checklist;
- rollback and incident runbooks;
- threat model and secret handling;
- known limitations;
- a verification record containing commands, versions, commit SHA, image digest, chart version, and sanitized results.

The README and architecture status remain “planned” until Phase 7A passes. After Phase 7A, the repository may say “local Kubernetes delivery implemented and verified; AWS EKS demonstration pending.” Only successful Phase 7B evidence may support “temporary AWS EKS deployment verified.”

## Explicit non-goals and non-guarantees

Phase 7 does not add or claim:

- consensus or leader election;
- linearizability;
- quorum durability;
- exactly-once execution;
- distributed transactions;
- automatic multi-region failover;
- arbitrary Byzantine fault tolerance;
- permanent production hosting;
- zero-downtime guarantees beyond tested rollout conditions;
- durability beyond the configured Kubernetes and AWS storage boundary.

The Kubernetes control plane, etcd dependency, storage provider, and AWS services introduce failure modes that must be documented honestly.

## Completion definition

Phase 7A is complete only when every local and CI acceptance gate passes on the committed implementation and verification evidence is published.

Phase 7B is complete only after separate user approval, successful temporary EKS verification, same-day destruction, and confirmation that no tagged Phase 7 billable resources remain.

The immutable `v0.6.0` tag is not moved or rewritten. Phase 7 receives a new version only after its applicable gates pass.
