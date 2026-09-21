# Phase 5 Verification

> **Record status:** Historical pre-release verification record. Phase 5 is now implemented and verified. The required gates below document the closure process at that milestone rather than unfinished current work.

At the time this record was created, it captured verification completed on the packaged Phase-5 tree plus environment-specific gates that still had to run before the phase could be closed. Those closure gates were subsequently completed.

## Verified on the packaged tree

The exact tree used to build `phase5-complete.zip` and `phase5-overlay.zip` was verified with:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m compileall -q src scripts tests
for f in scripts/*.sh; do bash -n "$f"; done
```

Fresh result:

```text
303 passed, 3 skipped
compileall=PASS
shell_syntax=PASS
```

The three skips are only the real-etcd integration tests. They are marked `etcd` and require `RUN_ETCD_INTEGRATION=1`, the `etcd3gw` runtime dependency, and a live etcd service.

### TLS/PKI verification

The development certificate generator was executed in a temporary/generated directory and checked with OpenSSL 3.5.5.

Verified properties:

```text
development CA: CA:TRUE
CA key usage: Certificate Sign, CRL Sign
node-1 certificate chain: OK
node-1 SAN: DNS:node-1, IP Address:127.0.0.1
node private-key mode: 0600
```

Generated keys were removed before packaging.

### Artifact hygiene

The packaged source tree was scanned for runtime/sensitive artifacts.

```text
tracked/generated *.key files in package: none
runtime *.db files in package: none
runtime *.db-wal files in package: none
runtime *.db-shm files in package: none
__pycache__/pytest caches in package: excluded
```

## Required WSL tooling gate

The packaging sandbox does not contain Ruff, Black, mypy, `grpcio-tools`, Docker, or a real etcd daemon. Therefore these gates are intentionally not claimed as completed here.

Run in WSL after applying the overlay:

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate

python -m pip install -e '.[dev]'
make proto
python -m black src tests scripts
python -m ruff check --fix src tests scripts
python -m black src tests scripts
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
```

Required outcome: every command exits zero.

## Required real-etcd integration gate

Docker must be available to WSL.

```bash
make phase5-etcd-integration
```

This must force and pass:

```text
tests/integration/test_etcd_registration.py
tests/integration/test_etcd_lease_expiry.py
tests/integration/test_etcd_outage.py
```

No etcd test may remain skipped in this gate.

## Required complete secure smoke

Run:

```bash
make phase5-secure-smoke
```

Required markers include:

```text
phase5_mtls_cluster=PASS
phase5_durable_crdts=PASS
phase5_schema_v1=PASS
phase5_unknown_ca_rejected=PASS
phase5_wrong_node_identity_rejected=PASS
phase5_plaintext_rejected=PASS
phase5_restart_durable_state=PASS
phase5_restart_new_swim_epoch=PASS
phase5_restart_same_causal_actor=PASS
phase5_restart_reconciliation=PASS
phase5_etcd_degraded_data_plane=PASS
phase5_etcd_registration_recovered=PASS
PHASE5_SMOKE=PASS
```

## Cleanup and repository hygiene

After managed smoke:

```bash
for port in 18000 18001 18002 2379; do
  ss -ltnp | grep ":$port" || echo "Port $port is free"
done
```

Then verify no secrets or runtime DBs are tracked:

```bash
if git ls-files | grep -E '(\.key$|certs/generated|\.db$|\.db-wal$|\.db-shm$)'; then
  echo "Sensitive/runtime artifact is tracked"
  exit 1
fi
```

## Release gate

Do not create `v0.5.0` until all WSL quality, real-etcd, secure-smoke, cleanup, and repository-hygiene checks pass on the feature branch, the reviewed branch is merged to `main`, and the same critical gates are rerun on merged `main`.

Final remote invariant:

```text
origin/main commit == v0.5.0^{} commit
```
