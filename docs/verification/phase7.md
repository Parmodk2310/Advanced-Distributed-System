# Phase 7 verification ledger

Status: **IN PROGRESS until fresh final evidence is attached to the exact final commit.**

No AWS resource is created by Phase 7A verification. Any Phase 7B AWS infrastructure must remain separately approved and temporary.

Do not create or move the `v0.7.0` tag until Phase 7A, the approved Phase 7B demonstration, teardown verification, and final repository hygiene all pass on the exact release commit.

## Phase 7A required evidence

- quality suite result
- deployment test count
- Docker image user/entrypoint/import
- image vulnerability scan
- SBOM path/digest
- kind node topology
- three application pods Ready
- CRDT convergence
- mTLS positive/negative tests
- persistence restart with same PVC
- rollback + healthy re-verification
- Terraform fmt/validate
- cleanup result

## Phase 7B required evidence

- approved source commit
- approved GHCR digest
- reviewed Terraform plan checksum
- ECR destination digest and source equality
- EKS cluster/worker identity
- three etcd members and PVCs
- three application pods and PVCs
- private verification
- temporary public verification
- persistence + rollback
- external endpoint deletion
- Terraform destroy
- zero unexpected Phase 7-tagged resources

Do not replace `IN PROGRESS` with `VERIFIED COMPLETE` until all applicable items are supported by fresh evidence from the final commit.
