# Phase 7 verification

## Status

**Local Kubernetes delivery implemented and verified; AWS EKS demonstration pending.**

Phase 7A provides a hardened OCI image, a three-node Helm StatefulSet, ephemeral per-pod mTLS, kind lifecycle, PVC restart verification, rollback verification, an inert-by-default AWS Terraform module, and GitHub Actions contracts.

Local evidence fields are written to `.phase7/evidence/`: `ready_replicas`, `health`, `metrics`, `mtls_rejection`, `crdt_convergence`, `persistence_restart`, `causal_read_after_restart`, and `phase7_local_release_gate`. Evidence contains no certificate or credential material.

Run `make phase7-release-gate` on a Docker-capable laptop. GitHub Actions must pass before a commit is recorded here as the final Phase 7A checkpoint.

## AWS Phase 7B

**PENDING SEPARATE APPROVAL.** No AWS resource creation is claimed. An exact Terraform plan, plan checksum, source commit, GHCR digest, full resource/cost inventory, budget alert, deployment duration, and teardown procedure must be approved before apply. Verification must be private-first, the temporary LoadBalancer must be deleted, and zero-resource checks must pass after destroy.

Phase 7 does not add consensus, linearizability, quorum durability, exactly-once execution, distributed transactions, multi-region recovery, or permanent production operations.
