# Phase 5E Recovery Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire persistence, etcd, SWIM, TLS, replica ownership, reconciliation, and readiness into one deterministic node lifecycle.

**Architecture:** A dedicated RecoveryCoordinator restores identity/clock/entries before normal CRDT traffic. The listener may bind before cluster join so control traffic can bootstrap, but client CRDT operations remain gated until a full recovery reconciliation pass completes.

**Tech Stack:** Python 3.12+, asyncio, Phase-5 persistence/coordination/security modules, Phase-4 SWIM/replication/anti-entropy, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-phase5-secure-persistence-design.md`

## Global Constraints

- Baseline release is `v0.4.0` at merge commit `e6cf2d52df49b6548ddfdd70aa0a212f69747dac`.
- Work only on branch `phase/5-secure-persistence`.
- Python remains `>=3.12`.
- Protobuf remains the application wire format.
- Existing `MessageType` numeric values `1..18` must not change.
- Existing `ErrorCode` numeric values `0..11` must not change.
- Phase-5 error codes append exactly: `12 PERSISTENCE_UNAVAILABLE`, `13 PERSISTENCE_BACKPRESSURE`, `14 RECOVERY_IN_PROGRESS`, `15 COORDINATION_UNAVAILABLE`, `16 TLS_AUTHENTICATION_FAILED`.
- `TLS_ENABLED=false` and `MTLS_REQUIRED=false` remain compatibility defaults; secure Phase-5 smoke enables both.
- Secure mode requires TLS 1.3 minimum.
- Persistence uses local SQLite with WAL and `synchronous=NORMAL` by default.
- A successful mutation is locally durable before ACK; it is not a quorum-durable ACK.
- etcd is coordination/discovery only; CRDT payloads never live in etcd.
- SWIM-lite remains the live membership/failure detector.
- Replication outbox remains in memory.
- Normal restart restores the durable causal actor/counter; SWIM incarnation still changes.
- CRDT classes remain storage/network independent.
- Blocking SQLite and etcd client calls must run off the asyncio event loop.
- New network tests use pytest-assigned explicit ports; do not add new direct `port=0` test fixtures.
- Generated certificates, private keys, SQLite DB/WAL/SHM files, and runtime logs must not be committed.
- Every production behavior follows TDD: failing test -> verify failure -> minimal implementation -> verify pass -> focused commit.

---

## File Map

Create:

```text
src/distsys/health/
├── __init__.py
└── state.py

src/distsys/recovery/
├── __init__.py
├── restore.py
├── reconciliation.py
└── coordinator.py
```

Modify:

```text
src/distsys/node.py
src/distsys/crdt_service.py
src/distsys/replication/service.py
src/distsys/replication/anti_entropy.py
src/distsys/cluster/service.py
src/distsys/utils/config.py
```

Tests:

```text
tests/unit/health/test_state.py
tests/unit/recovery/test_restore.py
tests/unit/recovery/test_reconciliation.py
tests/unit/recovery/test_coordinator.py

tests/integration/test_recovery_readiness.py
tests/integration/test_replica_recovery_reconciliation.py
tests/integration/test_etcd_outage.py
```

### Task 1: Health/readiness state model

**Files:**
- Create: `src/distsys/health/__init__.py`
- Create: `src/distsys/health/state.py`
- Test: `tests/unit/health/test_state.py`

**Interfaces:**
- `RecoveryPhase`: STARTING, OPENING_REPOSITORY, RESTORING, BINDING, COORDINATING, JOINING_CLUSTER, RECONCILING, READY, STARTUP_FAILED.
- `HealthState` tracks:
  - `liveness`
  - `readiness`
  - `coordination`
  - `cluster`
  - `recovery_phase`
  - last error strings.

- [ ] **Step 1: Write transition tests**

Invalid transition READY -> RESTORING without explicit reset must be rejected.

- [ ] **Step 2: Write coordination-degraded-with-ready test**

Health can be readiness ready while coordination degraded.

- [ ] **Step 3: Implement concurrency-safe async state with a small lock**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/health/test_state.py
git add src/distsys/health tests/unit/health
git commit -m "feat: model node recovery health state"
```

### Task 2: RestoreService

**Files:**
- Create: `src/distsys/recovery/restore.py`
- Test: `tests/unit/recovery/test_restore.py`

**Interfaces:**
- `RestoredNodeState(identity, causal_state, memory_store)`
- `RestoreService(repository, configured_node_id)`
- `async restore() -> RestoredNodeState`

**Behavior:**
1. integrity check,
2. load or initialize durable identity,
3. validate configured node id,
4. load clock or initialize actor frontier,
5. load entries,
6. rebuild `CrdtStore`,
7. ensure restored clock frontier dominates every persisted entry context.

- [ ] **Step 1: Write existing-state restore test**
- [ ] **Step 2: Write fresh-database initialization test**
- [ ] **Step 3: Write entry-context-frontier merge test**
- [ ] **Step 4: Write identity mismatch propagation test**
- [ ] **Step 5: Implement**
- [ ] **Step 6: Run and commit**

```bash
python -m pytest -q tests/unit/recovery/test_restore.py
git add src/distsys/recovery/restore.py tests/unit/recovery/test_restore.py
git commit -m "feat: restore durable node state"
```

### Task 3: Full-pass recovery reconciliation primitive

**Files:**
- Create: `src/distsys/recovery/reconciliation.py`
- Modify: `src/distsys/replication/anti_entropy.py`
- Modify: `src/distsys/replication/service.py`
- Test: `tests/unit/recovery/test_reconciliation.py`

**Interfaces:**
- AntiEntropyService adds deterministic:
  - `async reconcile_peer(peer, keys: tuple[str, ...] | None = None) -> ReconcileStats`
- ReplicationService exposes:
  - `async reconcile_peer(...)`
- `RecoveryReconciler.reconcile(store, selector, peers) -> RecoveryReconciliationResult`

**Behavior:**
- recalculate authority for every restored key,
- persist `last_authoritative`,
- for authoritative keys, perform one bounded full digest/state reconciliation pass against every currently ALIVE relevant replica peer,
- unavailable peer is recorded; reconciliation does not become a quorum requirement,
- non-owned keys remain stored but excluded from authoritative routing.

- [ ] **Step 1: Write authority recalculation test**
- [ ] **Step 2: Write stale-local/newer-remote test**
- [ ] **Step 3: Write concurrent-state merge test**
- [ ] **Step 4: Write unavailable-peer bounded-completion test**
- [ ] **Step 5: Implement deterministic anti-entropy entry point**
- [ ] **Step 6: Run Phase-4 anti-entropy regressions**

```bash
python -m pytest -q \
  tests/unit/recovery/test_reconciliation.py \
  tests/unit/test_anti_entropy.py \
  tests/integration/test_anti_entropy_convergence.py
```

- [ ] **Step 7: Commit**

```bash
git add src/distsys/recovery/reconciliation.py src/distsys/replication tests
git commit -m "feat: reconcile restored replicas before readiness"
```

### Task 4: Split replication startup into fast-path and anti-entropy phases

**Files:**
- Modify: `src/distsys/replication/service.py`
- Modify: `src/distsys/crdt_service.py`
- Test: `tests/unit/test_replication_service.py`

**Interfaces:**
- `ReplicationService.start_fast_path()`
- `ReplicationService.start_anti_entropy()`
- `ReplicationService.stop()`
- `CrdtService.start_fast_path()`
- `CrdtService.start_anti_entropy()`

Compatibility `start()` may call both in order for non-recovery tests.

- [ ] **Step 1: Write lifecycle test proving anti-entropy is not started by `start_fast_path()`**
- [ ] **Step 2: Write idempotent start/stop test**
- [ ] **Step 3: Implement split lifecycle**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/test_replication_service.py
git add src/distsys/replication/service.py src/distsys/crdt_service.py tests/unit/test_replication_service.py
git commit -m "refactor: separate replication recovery lifecycle"
```

### Task 5: ClusterService bootstrap-seed override

**Files:**
- Modify: `src/distsys/cluster/service.py`
- Test: `tests/unit/test_cluster_service.py`

**Interfaces:**
- Constructor optional:
  - `bootstrap_seeds: tuple[SeedAddress, ...] | None`
  - `peer_client` remains injectable.
- If override supplied, bootstrap uses it; otherwise existing `settings.cluster_seeds`.

- [ ] **Step 1: Write override-precedence test**
- [ ] **Step 2: Write legacy settings-seed regression**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/test_cluster_service.py
git add src/distsys/cluster/service.py tests/unit/test_cluster_service.py
git commit -m "feat: bootstrap cluster from discovered peers"
```

### Task 6: RecoveryCoordinator

**Files:**
- Create: `src/distsys/recovery/coordinator.py`
- Test: `tests/unit/recovery/test_coordinator.py`

**Interfaces:**
- `RecoveryCoordinator`
- `async prepare_persistence() -> RestoredNodeState`
- `async bootstrap_coordination(member) -> tuple[SeedAddress, ...]`
- `async reconcile(crdt_service) -> RecoveryReconciliationResult`
- updates shared HealthState at every phase.

- [ ] **Step 1: Write exact phase-order test**

Recorded transitions must equal:

```text
OPENING_REPOSITORY
RESTORING
COORDINATING
JOINING_CLUSTER
RECONCILING
READY
```

BINDING is owned by node between RESTORING and COORDINATING.

- [ ] **Step 2: Write startup-failure state test**
- [ ] **Step 3: Implement orchestration helpers; do not make coordinator own sockets**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/recovery/test_coordinator.py
git add src/distsys/recovery/coordinator.py tests/unit/recovery/test_coordinator.py
git commit -m "feat: coordinate phase five recovery lifecycle"
```

### Task 7: DistributedNode startup integration

**Files:**
- Modify: `src/distsys/node.py`
- Test: `tests/integration/test_recovery_readiness.py`
- Test: `tests/integration/test_durable_crdt_restart.py`

**Interfaces:**
- `DistributedNode` owns:
  - repository,
  - health state,
  - coordination service,
  - recovery coordinator,
  - TLS server/client contexts.
- Exact startup order follows the written spec.

- [ ] **Step 1: Write readiness gate test**

Block reconciliation using Event after server bind. Send direct CRDT mutation. Assert CRDT response error code 14 `RECOVERY_IN_PROGRESS`; no durable/memory state change.

- [ ] **Step 2: Write control-plane-during-recovery test**

Cluster JOIN/PING required for reconciliation remains processable while client CRDT mutation is gated.

- [ ] **Step 3: Implement startup order**

```text
executor
TLS contexts
repository open
restore
TLS server bind
coordination connect/discovery/lease
ClusterService bootstrap
CrdtService with durable actor/clock/store
replication fast path
reconciliation
anti-entropy background
READY
```

- [ ] **Step 4: Implement exception cleanup in strict reverse ownership order**
- [ ] **Step 5: Run**

```bash
python -m pytest -q \
  tests/integration/test_recovery_readiness.py \
  tests/integration/test_durable_crdt_restart.py
```

- [ ] **Step 6: Commit**

```bash
git add src/distsys/node.py tests/integration
git commit -m "feat: orchestrate durable node startup and readiness"
```

### Task 8: Real process restart and stale-state reconciliation

**Files:**
- Create/expand: `tests/integration/test_replica_recovery_reconciliation.py`

**Interfaces:**
- Three actual DistributedNode objects with persistent temp DB paths.

- [ ] **Step 1: Start three nodes and converge**
- [ ] **Step 2: Write key and capture node-2 durable causal actor + SWIM incarnation**
- [ ] **Step 3: Stop node-2**
- [ ] **Step 4: Advance key on surviving nodes**
- [ ] **Step 5: Recreate node-2 from same DB**
- [ ] **Step 6: Assert**
  - SWIM incarnation changed,
  - durable causal actor unchanged,
  - local counter did not regress,
  - stale disk state is reconciled to newer/concurrent live state,
  - final state is persisted.
- [ ] **Step 7: Reopen node-2 DB again and assert reconciled value remains**
- [ ] **Step 8: Run and commit**

```bash
python -m pytest -q tests/integration/test_replica_recovery_reconciliation.py
git add tests/integration/test_replica_recovery_reconciliation.py
git commit -m "test: verify crash recovery reconciliation"
```

### Task 9: Post-READY etcd degradation at node level

**Files:**
- Expand: `tests/integration/test_etcd_outage.py`
- Modify: `src/distsys/node.py` only if callback wiring is missing.

**Interfaces:**
- Full node data plane stays usable during etcd outage.

- [ ] **Step 1: Start secure/persistent node cluster with etcd healthy**
- [ ] **Step 2: Stop etcd**
- [ ] **Step 3: Wait for node coordination health degraded**
- [ ] **Step 4: Perform safe CRDT write/read through existing SWIM cluster**
- [ ] **Step 5: Restart etcd and wait for coordination healthy**
- [ ] **Step 6: Assert node UUID/causal actor unchanged**
- [ ] **Step 7: Run and commit**

```bash
python -m pytest -q tests/integration/test_etcd_outage.py
git add tests/integration/test_etcd_outage.py src/distsys/node.py
git commit -m "test: keep data plane available during etcd outage"
```
