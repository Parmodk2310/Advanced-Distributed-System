# Phase 7 verification ledger

Status: **VERIFIED COMPLETE**

Phase 7 was verified on 2026-09-17 against the exact final implementation commit:

```text
cd89ed476c7898cae9d0cb19158075ccfbd46d86
```

The AWS portion was a controlled, temporary EKS demonstration. It proved the
delivery lifecycle and was destroyed after evidence capture; this repository
does not claim that a permanently hosted production service is running.

## Immutable release identity

| Item | Verified value |
| --- | --- |
| Source commit | `cd89ed476c7898cae9d0cb19158075ccfbd46d86` |
| GHCR image digest | `sha256:6db4ce3304128c8e7aa119d0bc11a8092f1697687a47b68cef42f2b01231e68d` |
| Image evidence artifact digest | `sha256:7724020c9387f50a8601158982fbf72d0cbac949dc2829b4c879243a1efcd358` |
| SPDX SBOM artifact digest | `sha256:749f030421e7aae273412822e304ebfdc1982921cc871b96e20103d7db7993c9` |

## Final workflow evidence

| Gate | Run | Result | Evidence |
| --- | --- | --- | --- |
| Quality | [35180387246](https://github.com/Parmodk2310/Advanced-Distributed-System/actions/runs/35180387246) | **PASS** | Exact final commit |
| Image build, scan and SBOM | [35180387235](https://github.com/Parmodk2310/Advanced-Distributed-System/actions/runs/35180387235) | **PASS** | Signed immutable GHCR digest and uploaded artifact metadata |
| Local Kubernetes | [35180387466](https://github.com/Parmodk2310/Advanced-Distributed-System/actions/runs/35180387466) | **PASS** | Evidence digest `sha256:1b520980f2171dd6a160b564d9352085c777f63d8fa4c550b805b2dac716c16a` |
| Reviewed AWS plan | [35181947882](https://github.com/Parmodk2310/Advanced-Distributed-System/actions/runs/35181947882) | **PASS** | Plan artifact digest `sha256:739ec69f9a6170cb330329d623d8777bb47f7f1415001fadf25565a13c82d2bc` |
| AWS apply and verification | [35182138260](https://github.com/Parmodk2310/Advanced-Distributed-System/actions/runs/35182138260) | **PASS** | Evidence digest `sha256:7fa63cbb5753e913327a3e972e7793a8f819acd46f4e8675a85721e2225439cb` |
| AWS destroy and residual-resource check | [35183535307](https://github.com/Parmodk2310/Advanced-Distributed-System/actions/runs/35183535307) | **PASS** | Evidence digest `sha256:cbcf4bf03196f1286473ca9ee4f2cb98e49f5e697aee14909b09929f786eb9f9` |

GitHub Actions artifacts have finite retention. The run IDs, commit, image
digest and artifact digests above preserve the provenance record after the
downloadable archives expire.

## Phase 7A — local Kubernetes

The local release gate verified:

- non-root container execution and the expected entrypoint/import contract;
- image vulnerability and secret scanning plus SPDX SBOM generation;
- three application pods delivered through the Helm release contract;
- CRDT convergence and mTLS positive/negative behavior;
- persistence across pod restart using the same PVC;
- rollback followed by healthy re-verification;
- Terraform formatting/validation; and
- cluster and private TLS-material cleanup.

No AWS resource is created by Phase 7A verification, documentation changes or normal development commands.

## Phase 7B — temporary AWS EKS demonstration

The reviewed Terraform plan contained **23 additions, 0 changes and 0
deletions**. It used one `t3.medium` on-demand worker, no NAT Gateway, a
restricted EKS API allowlist, a USD 15 budget boundary and explicit expiration
metadata.

The controlled apply:

- downloaded and checksum-verified the reviewed plan;
- applied that exact plan without replanning;
- temporarily authorized only the GitHub runner /32 for EKS API access;
- promoted the approved GHCR digest into ECR without rebuilding;
- deployed three etcd members and three application replicas through Helm;
- verified the private cluster, persistence and rollback;
- exposed a temporary external endpoint only for external verification;
- removed that endpoint on the unconditional cleanup path; and
- restored the approved EKS API CIDRs.

The controlled destroy:

- uninstalled the application and etcd releases;
- deleted PVCs and waited for Kubernetes-created EBS volumes to converge;
- destroyed the Terraform-managed EKS, ECR and network infrastructure;
- ran the residual-resource verifier successfully; and
- retained only the separately managed Terraform state bucket and lock table.

After teardown, `AWS_PHASE7_ENABLED` was set back to `false`.

No `v0.7.0` tag or GitHub release was created by this documentation closure.

## Verified boundary

This evidence demonstrates a reproducible build, local Kubernetes release,
controlled AWS EKS deployment, persistence check, rollback, external smoke
verification and complete teardown for the tested configuration.

It does **not** establish:

- multi-AZ or node-level high availability—the demonstration used one worker;
- a permanently hosted production service;
- production SLOs or internet-scale capacity;
- multi-region disaster recovery; or
- consensus, linearizability or quorum-durable acknowledgements.
