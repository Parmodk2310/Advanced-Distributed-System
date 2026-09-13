# Phase 5B Durable CRDT Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every visible local mutation and incoming replicated/repair state cross the durable repository boundary before it becomes acknowledged or visible.

**Architecture:** Add staged causal allocation so a failed SQLite transaction cannot advance only memory. A durable state adapter wraps the existing in-memory `CrdtStore`; Phase-4 replication components continue using store-like methods, but merges persist first and install memory second.

**Tech Stack:** Python 3.12+, Phase-4 causal/CRDT/replication code, Phase-5 StateRepository, Protobuf, pytest.

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
src/distsys/storage/protocol.py
src/distsys/persistence/durable_store.py
```

Modify:

```text
src/distsys/causal/clock.py
src/distsys/storage/models.py
src/distsys/storage/crdt_store.py
src/distsys/crdt_service.py
src/distsys/replication/service.py
src/distsys/replication/causal_repair.py
src/distsys/replication/anti_entropy.py
proto/messages.proto
src/distsys/proto/messages_pb2.py
src/distsys/proto/messages_pb2.pyi
```

Create tests:

```text
tests/unit/persistence/test_durable_store.py
tests/integration/test_durable_crdt_restart.py
tests/integration/test_durable_causal_clock.py
tests/integration/test_persistence_backpressure.py
tests/integration/test_durable_replica_merge.py
```

### Task 1: Staged CausalClock allocation

**Files:**
- Modify: `src/distsys/causal/clock.py`
- Test: `tests/unit/test_causal_clock.py`

**Interfaces:**
- Keep existing `allocate` behavior for Phase-4 callers.
- Add:
  - `CausalAllocation(dot, frontier)`
  - `async with clock.staged_allocation(observed) as allocation`
  - `allocation.commit()`
  - `async clock.restore(frontier)`

**Required semantics:**
- entering staged allocation holds the clock lock,
- candidate Dot/frontier are computed but not installed,
- `commit()` marks the candidate,
- context exit installs candidate only when committed and no exception occurred,
- exception/no-commit leaves in-memory frontier unchanged.

- [ ] **Step 1: Write rollback test**

```python
@pytest.mark.asyncio
async def test_staged_allocation_without_commit_does_not_advance_clock():
    actor = CausalActor("node-0", 500)
    clock = CausalClock(actor)
    before = await clock.frontier()
    async with clock.staged_allocation() as allocation:
        assert allocation.dot.counter == 1
    assert await clock.frontier() == before
```

- [ ] **Step 2: Write commit test**
- [ ] **Step 3: Write exception rollback test**
- [ ] **Step 4: Verify RED**
- [ ] **Step 5: Implement staged allocation with the existing internal lock**
- [ ] **Step 6: Reimplement legacy `allocate()` through staged allocation + immediate commit**
- [ ] **Step 7: Run**

```bash
python -m pytest -q tests/unit/test_causal_clock.py
```

Expected: existing Phase-4 clock tests plus new tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/distsys/causal/clock.py tests/unit/test_causal_clock.py
git commit -m "feat: add transactional causal clock allocation"
```

### Task 2: Shared CRDT store protocol and pure merge helper

**Files:**
- Create: `src/distsys/storage/protocol.py`
- Modify: `src/distsys/storage/models.py`
- Modify: `src/distsys/storage/crdt_store.py`
- Test: `tests/unit/test_crdt_store.py`

**Interfaces:**
- Produce `CrdtStateStore` protocol covering methods consumed by replication:
  - `get`
  - `snapshot`
  - `key_lock`
  - `replace`
  - `merge_entry`
  - `merge_metadata`
  - `keys`
  - `snapshot_all`
- Produce pure `merge_entries(left, right) -> StoredCrdtEntry`.

- [ ] **Step 1: Write pure merge tests**

Assert:
- same-type entries merge state/version/context,
- differing types raise `TypeError`,
- input entries are unchanged.

- [ ] **Step 2: Move existing merge logic out of `CrdtStore.merge_entry` into `merge_entries`**
- [ ] **Step 3: Make `CrdtStore.merge_entry` delegate to pure helper**
- [ ] **Step 4: Run**

```bash
python -m pytest -q tests/unit/test_crdt_store.py
```

- [ ] **Step 5: Commit**

```bash
git add src/distsys/storage
git commit -m "refactor: expose crdt state store contract"
```

### Task 3: DurableCrdtStore adapter

**Files:**
- Create: `src/distsys/persistence/durable_store.py`
- Test: `tests/unit/persistence/test_durable_store.py`

**Interfaces:**
- `DurableCrdtStore(memory, repository, clock)` implements `CrdtStateStore`.
- Additional:
  - `async commit_local(entry, frontier, expected_type=None, deadline=None)`
  - `async restore_entries(entries)`
  - `memory` property for diagnostic access.

**Persistence order for remote state:**
1. key lock,
2. read memory entry,
3. compute merged entry,
4. compute committed causal frontier,
5. repository `commit_observed_entry`,
6. memory replace,
7. clock observe/restore committed frontier.

- [ ] **Step 1: Write remote-merge ordering test**

Use fake repository that records `"persist"` and monkeypatched memory store that records `"memory"`. Assert sequence exactly:

```python
assert events == ["persist", "memory"]
```

- [ ] **Step 2: Write repository-failure test**

Repository raises `PersistenceUnavailableError`; assert memory store remains unchanged.

- [ ] **Step 3: Write metadata-only durability test**

`merge_metadata` advances causal context; reopen fake durable state and assert updated context was the one persisted.

- [ ] **Step 4: Verify RED**
- [ ] **Step 5: Implement adapter**
- [ ] **Step 6: Run**

```bash
python -m pytest -q tests/unit/persistence/test_durable_store.py
```

- [ ] **Step 7: Commit**

```bash
git add src/distsys/persistence/durable_store.py tests/unit/persistence/test_durable_store.py
git commit -m "feat: add durable crdt store adapter"
```

### Task 4: Append Phase-5 ErrorCode values

**Files:**
- Modify: `proto/messages.proto`
- Generate: `src/distsys/proto/messages_pb2.py`
- Generate: `src/distsys/proto/messages_pb2.pyi`
- Test: `tests/unit/test_message.py`

**Interfaces:**
- Existing `0..11` unchanged.
- Append exactly:
  - 12 `PERSISTENCE_UNAVAILABLE`
  - 13 `PERSISTENCE_BACKPRESSURE`
  - 14 `RECOVERY_IN_PROGRESS`
  - 15 `COORDINATION_UNAVAILABLE`
  - 16 `TLS_AUTHENTICATION_FAILED`

- [ ] **Step 1: Add numeric-stability test covering 0..16**
- [ ] **Step 2: Run test and verify RED for missing Phase-5 values**
- [ ] **Step 3: Append enum values to Protobuf**
- [ ] **Step 4: Regenerate**

```bash
make proto
```

- [ ] **Step 5: Run**

```bash
python -m pytest -q tests/unit/test_message.py
```

- [ ] **Step 6: Commit**

```bash
git add proto/messages.proto src/distsys/proto tests/unit/test_message.py
git commit -m "feat: append phase five error codes"
```

### Task 5: Inject restored causal/store state into CrdtService

**Files:**
- Modify: `src/distsys/crdt_service.py`
- Test: `tests/integration/test_crdt_local_operations.py`
- Test: `tests/integration/test_durable_causal_clock.py`

**Interfaces:**
- Constructor adds optional:
  - `actor: CausalActor | None`
  - `clock: CausalClock | None`
  - `store: CrdtStateStore | None`
  - `commit_local: Callable[[StoredCrdtEntry, VersionVector, Deadline], Awaitable[StoredCrdtEntry]] | None`
- Compatibility path remains: without injections, Phase-4 behavior derives actor from local SWIM member.

- [ ] **Step 1: Write injected-actor test**

Construct cluster member with SWIM incarnation 900 but inject durable actor `node-0@500`; assert service actor is `@500`.

- [ ] **Step 2: Write legacy-construction regression test**

No injected actor/clock/store; assert actor still derives from cluster local member as before.

- [ ] **Step 3: Implement constructor injection without changing default Phase-4 behavior**
- [ ] **Step 4: Run**

```bash
python -m pytest -q \
  tests/integration/test_crdt_local_operations.py \
  tests/integration/test_durable_causal_clock.py
```

- [ ] **Step 5: Commit**

```bash
git add src/distsys/crdt_service.py tests/integration/test_durable_causal_clock.py
git commit -m "feat: inject durable causal state into crdt service"
```

### Task 6: Durable local mutation before ACK

**Files:**
- Modify: `src/distsys/crdt_service.py`
- Test: `tests/integration/test_durable_crdt_restart.py`
- Test: `tests/integration/test_persistence_backpressure.py`

**Interfaces:**
- Durable mutation uses `clock.staged_allocation`.
- Persistence commit happens before:
  - memory state visibility,
  - replication publish,
  - success response.

- [ ] **Step 1: Write commit-order test**

Fake `commit_local` blocks on Event. Start mutation task. While blocked:
- `store.get(key)` remains old/None,
- replication fake has no publish,
- mutation task not complete.

Release persistence; assert memory/publish/response occur.

- [ ] **Step 2: Write persistence-failure test**

`commit_local` raises `PersistenceUnavailableError`; assert:
- response error code 12,
- no local state mutation,
- clock counter unchanged,
- outbox reservation is cancelled.

- [ ] **Step 3: Write persistence-backpressure test**

`commit_local` raises `PersistenceBackpressureError`; assert error code 13 and unchanged state.

- [ ] **Step 4: Modify mutation sequence**

Inside key lock:

```text
staged causal allocation
compute next CRDT entry
await durable commit
commit causal allocation
publish replication
respond
```

Cancel replication reservation on every pre-publish failure.

- [ ] **Step 5: Run**

```bash
python -m pytest -q \
  tests/integration/test_durable_crdt_restart.py \
  tests/integration/test_persistence_backpressure.py
```

- [ ] **Step 6: Commit**

```bash
git add src/distsys/crdt_service.py tests/integration
git commit -m "feat: commit crdt mutations durably before acknowledgement"
```

### Task 7: Durable replica, causal-repair, and anti-entropy merges

**Files:**
- Modify: `src/distsys/replication/service.py`
- Modify: `src/distsys/replication/causal_repair.py`
- Modify: `src/distsys/replication/anti_entropy.py`
- Test: `tests/integration/test_durable_replica_merge.py`
- Re-run: Phase-4 repair/convergence tests

**Interfaces:**
- Replication components depend on `CrdtStateStore`, not concrete `CrdtStore`.
- With `DurableCrdtStore`, existing calls to `merge_entry` and `merge_metadata` persist-before-memory automatically.

- [ ] **Step 1: Write incoming replication failure test**

Repository fails during merge; server must not return successful CRDT replication response and memory must not contain merged state.

- [ ] **Step 2: Write successful incoming replication reopen test**

Replicate state, create fresh repository/store objects on same DB, load entries, assert replicated state exists.

- [ ] **Step 3: Update type annotations/interfaces only where required**
- [ ] **Step 4: Run Phase-4 convergence regressions**

```bash
python -m pytest -q \
  tests/integration/test_crdt_async_replication.py \
  tests/integration/test_causal_read_repair.py \
  tests/integration/test_causal_write_repair.py \
  tests/integration/test_anti_entropy_convergence.py \
  tests/integration/test_durable_replica_merge.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/distsys/replication tests/integration/test_durable_replica_merge.py
git commit -m "feat: make replica repair state durable"
```

### Task 8: Service-level restart proof

**Files:**
- Expand: `tests/integration/test_durable_crdt_restart.py`
- Expand: `tests/integration/test_durable_causal_clock.py`

**Interfaces:**
- Proves repository + CRDT service semantics before full node recovery orchestration.

- [ ] **Step 1: Write state reopen test**

Mutate all four CRDT types through durable service, close repository, reopen, restore entries into new memory store, assert values.

- [ ] **Step 2: Write Dot continuity test**

First process writes local Dot counter N; reopen same DB; restore causal actor/frontier; next mutation produces N+1 with same causal actor.

- [ ] **Step 3: Run complete 5B gate**

```bash
python -m pytest -q \
  tests/unit/test_causal_clock.py \
  tests/unit/persistence \
  tests/integration/test_durable_crdt_restart.py \
  tests/integration/test_durable_causal_clock.py \
  tests/integration/test_persistence_backpressure.py \
  tests/integration/test_durable_replica_merge.py
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_durable_crdt_restart.py tests/integration/test_durable_causal_clock.py
git commit -m "test: prove durable causal crdt restart semantics"
```
