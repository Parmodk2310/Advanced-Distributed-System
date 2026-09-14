# Phase 6 v5 Verification Record

## Artifact-side verification

Fresh checks performed on this v5 artifact:

```text
PYTHONPATH=src python -m pytest -q \
  tests/unit/observability \
  tests/unit/benchmarking \
  tests/unit/chaos \
  tests/unit/patches \
  tests/integration/test_monitoring_config.py

26 passed
```

The health endpoint test was repeated five isolated times after changing the listener to bind/listen explicitly before asyncio takes ownership.

```text
health_repeat_5x=PASS
python -m compileall -q src scripts tests patches
PASS
bash -n scripts/*.sh
PASS
JSON/YAML configuration parse
PASS
```

Patcher recovery coverage verifies duplicate config recovery, routing-import recovery, already-instrumented replication/persistence recovery, and idempotent test-harness timing relaxation.

## Phase 1–5 compatibility evidence from the real repository

The user's Phase 5 secure smoke passed all mTLS, durable CRDT, restart, reconciliation, and etcd degraded/recovery checks before v5. The remaining SWIM quality failures were timing-sensitive: `test_node_rejoin` failed in one full-suite run and passed in the next without a runtime code change. v5 therefore changes only the affected integration-test DEAD wait budget from 2.0 to 3.0 seconds; it does not change failure-detector settings or runtime semantics.

## What still requires the real repository

Before Phase 6 is complete, the WSL checkout must still pass `make quality`, `make phase5-secure-smoke`, and `make phase6-release-gate`, including monitoring, tracing, chaos cleanup/recovery, and quick benchmark budgets.
