# Phase 4 Verification Record

**Target:** `v0.4.0`  
**Base:** `v0.3.0`  
**Feature:** Causal Consistency & CRDT Replication

## Sandbox verification

The completed Phase-4 tree was tested in the artifact environment with:

```bash
PYTHONPATH=src python -m pytest -q
```

Result:

```text
222 passed
```

Focused failure/convergence gate:

```bash
PYTHONPATH=src python -m pytest -q \
  tests/integration/test_replication_backpressure.py \
  tests/integration/test_orset_concurrent_partition.py \
  tests/integration/test_mvregister_concurrent_partition.py \
  tests/integration/test_anti_entropy_convergence.py \
  tests/integration/test_crdt_node_rejoin.py \
  tests/integration/test_crdt_replica_reassignment.py
```

Result:

```text
6 passed
```

Normal three-node smoke result (the repair flag may be true or false depending on whether fast replication wins the race):

```text
phase3_membership_converged=PASS
gcounter_remote_causal_read=PASS
causal_read_repair_performed=<timing dependent fast-path result>
orset_operations=PASS
mvregister_operation=PASS
phase4_smoke=PASS
```

Managed failure/rejoin result:

```text
phase4_managed_failure_detection=PASS
phase4_reduced_rf_write=PASS
phase4_rejoin_new_causal_epoch=PASS
phase4_rejoin_targeted_causal_repair=PASS
phase4_rejoin_recovery=PASS
```

After normal smoke shutdown:

```text
port 18000 free
port 18001 free
port 18002 free
```

Compilation check:

```bash
PYTHONPATH=src python -m compileall -q src scripts tests
```

Result: PASS.

## Verified behaviors represented by tests

- incarnation-scoped causal actors and non-colliding restart dots,
- VersionVector before/after/equal/concurrent comparison,
- missing causal frontier calculation,
- session-wide CausalToken propagation,
- GCounter and PNCounter state merge,
- observed-remove ORSet with unseen concurrent add survival,
- MVRegister concurrent-value preservation and later causal resolution,
- per-key CrdtStore locking and type consistency,
- Phase-3 ring reuse for CRDT replica selection,
- bounded/coalescing generation-safe replication outbox,
- pre-mutation `REPLICATION_BACKPRESSURE`,
- asynchronous state replication,
- local causal read fast path,
- targeted causal read repair,
- targeted causal write repair,
- `CAUSAL_UNAVAILABLE` for unreachable causal frontier,
- read-your-writes,
- monotonic reads,
- monotonic writes,
- writes-follow-reads,
- cross-key causal session dependency,
- digest-driven anti-entropy,
- node restart with new causal epoch and state reconstruction,
- replica reassignment and non-authoritative old copies,
- any-node ingress with single-hop authoritative forwarding.

## Environment limitation

The artifact environment does not have Ruff, Black, mypy, or `grpcio-tools`
installed and cannot reach the package index. Therefore this environment cannot
claim those four developer quality gates. The repository includes the same
pinned tools in `pyproject.toml`/`requirements-dev.txt`; the authoritative final
gate must be run in the user's WSL environment:

```bash
make proto
python -m black src tests scripts
make quality
```
