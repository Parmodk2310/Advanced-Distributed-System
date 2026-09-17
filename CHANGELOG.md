# Changelog

All notable project milestones are documented here.

Historical tags were engineering checkpoints rather than formal GitHub
Releases. `v0.7.0` is the first formal GitHub Release.

## [Unreleased]

No unreleased changes are recorded.

## [v0.7.0] — Verified Kubernetes and AWS Delivery Lifecycle

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

### Phase 7 AWS demonstration identity

- Final implementation checkpoint:
  `cd89ed476c7898cae9d0cb19158075ccfbd46d86`.
- Latest complete automated suite: 435 passed, 8 skipped.
- GHCR image:
  `sha256:6db4ce3304128c8e7aa119d0bc11a8092f1697687a47b68cef42f2b01231e68d`.
- Reviewed Terraform plan: 23 additions, 0 changes, 0 deletions.
- Temporary AWS apply, verification, rollback, and teardown.
- Zero unexpected tagged resources after cleanup.
- AWS execution gate disabled after the demonstration.

### v0.7.0 release identity

The release candidate passed the Quality, Phase 7 Local Kubernetes, and Phase 7 Image workflows.

- Release source commit: `7995d5342e5c40d83ee36beeed10ba50ce70f00f`.
- GHCR manifest digest: `sha256:c571c604cf310ddbf8c3c7ea1c9b605ffc8fdf1da5ec755422035643552e3a5f`.
- SPDX SBOM SHA-256: `ba37ef2346f219b1b68468f24c56f9f1ae4f088df772d5b254e5762e9f69e4c9`.
- Image evidence artifact SHA-256: `23291c9c93646a2466acc3a595dadd393509d5edff8f25c9826a191d16c314d8`.
- Image workflow: `35208700672`; local Kubernetes: `35208700515`; Quality: `35208700539`.
- The immutable digest was scanned, tested in kind, published to GHCR, and keyless-signed.

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

The formal `v0.7.0` release uses
[`docs/releases/v0.7.0.md`](docs/releases/v0.7.0.md) as its durable release
record and keeps the exact source commit and image digest visible.
