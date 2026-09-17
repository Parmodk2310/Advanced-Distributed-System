# Changelog

All notable project milestones are documented here.

Historical tags were engineering checkpoints rather than formal GitHub
Releases. `v0.7.0` is intended to be the first formal release after the
public-readiness review.

## [Unreleased]

### Public-readiness preparation

- Recruiter-first README
- Apache-2.0 license
- Contribution and security policies
- Formal `v0.7.0` release notes
- Public-readiness checklist

No visibility change is implied by this section.

## [v0.7.0] — Planned first formal GitHub Release

**Title:** Verified Kubernetes and AWS Delivery Lifecycle

### Added

- Hardened non-root multi-stage OCI image.
- Immutable image verification and digest-based promotion.
- SPDX SBOM generation.
- Gitleaks and Trivy release gates.
- Helm packaging for the runtime and cloud-demo etcd.
- Kubernetes schema and OPA/Conftest policy validation.
- Three-replica local kind verification.
- PVC persistence and same-volume restart verification.
- Deliberately failed Helm upgrade and verified rollback.
- Terraform-managed temporary AWS EKS delivery.
- GitHub OIDC authentication for AWS workflows.
- Reviewed-plan apply flow.
- GHCR-to-ECR artifact copy without rebuild.
- Temporary external endpoint verification.
- Full AWS teardown and residual-resource verification.

### Verified

- Final implementation checkpoint:
  `cd89ed476c7898cae9d0cb19158075ccfbd46d86`.
- Latest complete automated suite: 435 passed, 8 skipped.
- GHCR image:
  `sha256:6db4ce3304128c8e7aa119d0bc11a8092f1697687a47b68cef42f2b01231e68d`.
- Reviewed Terraform plan: 23 additions, 0 changes, 0 deletions.
- Temporary AWS apply, verification, rollback, and teardown.
- Zero unexpected tagged resources after cleanup.
- AWS execution gate disabled after the demonstration.

### Boundaries

- One `t3.medium` worker was used.
- No multi-AZ or node-level HA claim.
- No permanent hosted production service.
- No consensus, linearizability, quorum durability, exactly-once distributed
  execution, or distributed ACID transaction guarantee.

## [v0.6.0] — Observability, chaos, and performance

### Added

- Prometheus metrics and dedicated health endpoints.
- OpenTelemetry tracing, OTLP collection, Tempo, and Grafana.
- Toxiproxy delay/partition experiments.
- Managed etcd outage and node-kill recovery.
- Reproducible task and CRDT benchmarks.
- p50/p95/p99 and throughput reporting.
- Explicit chaos safety opt-in.

## Phase 5 milestone — no `v0.5.0` tag

No `v0.5.0` Git tag was created historically.

This section records the Phase 5 implementation milestone only; it is **not** a
retroactive release or tag.

### Added

- SQLite WAL-backed local durable state.
- Durable causal actor/counter/frontier.
- Persist-before-memory durable mutation flow.
- Restart restore and replica reconciliation.
- Recovery-readiness gating.
- SQLite online backup.
- etcd discovery and leases.
- TLS 1.3 and mutual TLS.
- Logical node identity verification against certificate SANs.

## [v0.4.0] — Causal consistency and CRDT replication

### Added

- Version vectors, causal tokens, dotted mutation identity.
- Read-your-writes and monotonic session semantics.
- GCounter, PNCounter, ORSet, and MVRegister.
- Targeted causal repair and replica-aware anti-entropy.

## [v0.3.0] — Distributed cluster and routing

### Added

- Static-seed bootstrap.
- SWIM-style membership.
- ALIVE / SUSPECT / DEAD states.
- Incarnation-aware merge and rejoin.
- Gossip convergence.
- SHA-256 consistent hashing.
- Deterministic ownership and failover routing.
- Direct and indirect failure probes.

## [v0.2.0] — Compute and resilience

### Added

- Bounded process-pool execution.
- Bounded CPU admission.
- Rate limiting and backpressure.
- Request deadlines.
- Full-jitter retry policy.
- Circuit breaker state machine.
- Structured protocol errors.

## [v0.1.0] — Async protocol foundation

### Added

- Async TCP foundation.
- Protobuf protocol.
- Framing and validation.
- Initial request/response path.

## Versioning note

Do not create a synthetic `v0.5.0` tag solely to make the sequence visually
continuous.

When `v0.7.0` is published, use
[`docs/releases/v0.7.0.md`](docs/releases/v0.7.0.md) as the release body and
keep the exact source commit and image digest visible.
