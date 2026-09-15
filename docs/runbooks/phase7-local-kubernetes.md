# Phase 7 local Kubernetes runbook

## Prerequisites

Use Python 3.12, Docker with BuildKit, kind 0.26.0, kubectl 1.32.2, and Helm 3.17.3. The laptop should have at least 4 CPU cores, 8 GiB RAM, and 10 GiB free disk space.

## Required kind verification

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
make phase7-release-gate
```

The gate builds the non-root image, creates `distsys-phase7`, generates ephemeral TLS identities, installs the three-node StatefulSet, verifies mTLS and CRDT convergence, restarts a pod to prove PVC recovery, exercises Helm rollback, and removes the cluster. Sanitized JSON remains in `.phase7/evidence/`; private keys are removed.

For interactive inspection use `make phase7-local-up`, run the three `phase7-*-verify` targets, then always run `make phase7-local-down`.

## Optional k3d parity

Run `make phase7-k3d-verify`. The same image, chart values, and verifier are used; kind remains the required CI contract.

This local demonstration does not prove consensus, linearizability, quorum durability, exactly-once processing, distributed transactions, multi-region behavior, or production availability.
