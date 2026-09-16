# Phase 7 verification

## Status

**Local Kubernetes delivery implemented and verified; AWS EKS demonstration pending.**

Phase 7A provides a hardened OCI image, a three-node Helm StatefulSet, ephemeral per-pod mTLS, kind lifecycle, PVC restart verification, rollback verification, an inert-by-default AWS Terraform module, and GitHub Actions contracts.

Local evidence fields are written to `.phase7/evidence/`: `ready_replicas`, `health`, `metrics`, `mtls_rejection`, `crdt_convergence`, `persistence_restart`, `causal_read_after_restart`, and `phase7_local_release_gate`. Evidence contains no certificate or credential material.

Run `make phase7-release-gate` on a Docker-capable laptop. GitHub Actions must pass before a commit is recorded here as the final Phase 7A checkpoint.


## Verified Phase 7A checkpoint

- Source commit: [`93c0553`](https://github.com/Parmodk2310/Advanced-Distributed-System/commit/93c0553dbcd72e165cc14c9e87290e2e610e335d)
- Repository quality: [GitHub Actions run 35057943329](https://github.com/Parmodk2310/Advanced-Distributed-System/actions/runs/35057943329)
- Image, security, SBOM, provenance, and local lifecycle: [GitHub Actions run 35057943330](https://github.com/Parmodk2310/Advanced-Distributed-System/actions/runs/35057943330)
- Independent local release gate and Terraform validation: [GitHub Actions run 35057943309](https://github.com/Parmodk2310/Advanced-Distributed-System/actions/runs/35057943309)
- Verified image: `ghcr.io/parmodk2310/distsys-node@sha256:cc5631dc723058f9d71b1c37fce566706c317d12d50a1c98f6c24139ad448cae`

The retained Actions artifacts contain sanitized JSON verification evidence, digest-bound provenance metadata, and the SPDX SBOM. GitHub-native attestations are unavailable for user-owned private repositories and activate automatically if the repository becomes public. Ephemeral certificates, keys, Kubernetes clusters, and local workspaces are removed by unconditional cleanup steps.

## AWS Phase 7B

**PENDING SEPARATE APPROVAL.** No AWS resource creation is claimed. An exact Terraform plan, plan checksum, source commit, GHCR digest, full resource/cost inventory, budget alert, deployment duration, and teardown procedure must be approved before apply. Verification must be private-first, the temporary LoadBalancer must be deleted, and zero-resource checks must pass after destroy.

Phase 7 does not add consensus, linearizability, quorum durability, exactly-once execution, distributed transactions, multi-region recovery, or permanent production operations.
