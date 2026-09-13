# Phase 4B CRDT Core and Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement GCounter, PNCounter, observed-remove ORSet, MVRegister, and an atomic in-memory CrdtStore.

**Architecture:** CRDT states are immutable and merge by state. The store separates per-key `state_version` from session `causal_context`, uses per-key locking for mutation/merge, and rejects CRDT type changes for an existing key.

**Tech Stack:** Python 3.12+, dataclasses, typing.Protocol, asyncio, JSON, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-phase4-causal-crdt-design.md`

## Global Constraints

- Base release: `v0.3.0`; feature branch: `phase/4-causal-crdt`.
- Python: 3.12+.
- Protobuf remains the wire format.
- Existing `MessageType` values 1-11 must not change.
- Existing `ErrorCode` values 0-8 must not change.
- `CRDT_ENABLED=false` by default; enabling CRDT requires clustering.
- Default replication factor: 3.
- Default replication outbox capacity: 500 unique `(peer,key)` pairs.
- Default replication workers: 2.
- Default anti-entropy interval: 2.0 seconds.
- Default anti-entropy batch size: 100.
- Phase-1/2/3 behavior and tests must remain green.
- New network integration tests use pytest-assigned explicit ports, never direct `port=0`.
- Request-path routing, causal repair, forwarding, and merge share the original Phase-3 monotonic deadline.
- Phase 4 remains in-memory only: no WAL, disk persistence, quorum, consensus, transaction, whole-key delete, Merkle tree, hinted handoff, or exactly-once claim.
- Follow TDD for each task: failing test -> minimal implementation -> passing test -> focused commit.

---

## File Map

```text
src/distsys/crdt/
├── __init__.py
├── base.py
├── types.py
├── gcounter.py
├── pncounter.py
├── orset.py
└── mvregister.py

src/distsys/storage/
├── __init__.py
├── models.py
└── crdt_store.py
```

### Task 1: Common CRDT types and GCounter

**Files:**
- Create: `src/distsys/crdt/base.py`
- Create: `src/distsys/crdt/types.py`
- Create: `src/distsys/crdt/gcounter.py`
- Create: `src/distsys/crdt/__init__.py`
- Test: `tests/unit/test_gcounter.py`

**Interfaces:**
- `CrdtType`: GCOUNTER, PNCOUNTER, ORSET, MVREGISTER
- `CRDT` Protocol: `merge`, `to_dict`
- `GCounter.increment(actor, amount=1)`, `value`, `merge`

- [ ] **Step 1: Write failing GCounter tests**

```python
def test_increment_and_merge():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    left = GCounter().increment(a, 5).increment(b, 2)
    right = GCounter().increment(a, 3).increment(b, 4)
    merged = left.merge(right)
    assert merged.value() == 9
    assert merged == right.merge(left)
    assert merged.merge(merged) == merged
```

- [ ] **Step 2: Write invalid amount test**
- [ ] **Step 3: Run failure**

```bash
python -m pytest -q tests/unit/test_gcounter.py
```

- [ ] **Step 4: Implement deterministic actor-component state**
- [ ] **Step 5: Run and commit**

```bash
python -m pytest -q tests/unit/test_gcounter.py
git add src/distsys/crdt tests/unit/test_gcounter.py
git commit -m "feat: add grow only counter crdt"
```

### Task 2: PNCounter

**Files:**
- Create: `src/distsys/crdt/pncounter.py`
- Test: `tests/unit/test_pncounter.py`

**Interfaces:**
- `PNCounter(positive: GCounter, negative: GCounter)`
- `increment`, `decrement`, `value`, `merge`

- [ ] **Step 1: Write failing composition tests**

```python
def test_increment_decrement_merge():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    left = PNCounter().increment(a, 5).decrement(a, 1)
    right = PNCounter().increment(b, 4).decrement(b, 2)
    assert left.merge(right).value() == 6
```

- [ ] **Step 2: Run failure**
- [ ] **Step 3: Implement via two GCounters**
- [ ] **Step 4: Add commutative/associative/idempotent merge assertions**
- [ ] **Step 5: Run and commit**

```bash
python -m pytest -q tests/unit/test_pncounter.py
git add src/distsys/crdt tests/unit/test_pncounter.py
git commit -m "feat: add pn counter crdt"
```

### Task 3: ORSet

**Files:**
- Create: `src/distsys/crdt/orset.py`
- Test: `tests/unit/test_orset.py`

**Interfaces:**
- `add(element: str, dot: Dot)`
- `remove(element: str)`
- `contains(element)`, `value`, `merge`

- [ ] **Step 1: Write observed-remove and concurrent-add tests**

```python
def test_unseen_concurrent_add_survives_remove():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    base = ORSet().add("python", Dot(a, 1))
    removed = base.remove("python")
    concurrent = base.add("python", Dot(b, 1))
    assert removed.merge(concurrent).value() == frozenset({"python"})
```

- [ ] **Step 2: Write duplicate-merge/idempotence test**
- [ ] **Step 3: Write string-only validation test**
- [ ] **Step 4: Run failure**

```bash
python -m pytest -q tests/unit/test_orset.py
```

- [ ] **Step 5: Implement add-dot map + removed-dot set**
- [ ] **Step 6: Run and commit**

```bash
python -m pytest -q tests/unit/test_orset.py
git add src/distsys/crdt tests/unit/test_orset.py
git commit -m "feat: add observed remove set crdt"
```

### Task 4: MVRegister

**Files:**
- Create: `src/distsys/crdt/mvregister.py`
- Test: `tests/unit/test_mvregister.py`

**Interfaces:**
- `write(value: object, dot: Dot)`
- `values() -> tuple[object, ...]`
- `merge`

- [ ] **Step 1: Write concurrent-value test**

```python
def test_concurrent_values_survive():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    left = MVRegister().write("medium", Dot(a, 1))
    right = MVRegister().write("high", Dot(b, 1))
    assert set(left.merge(right).values()) == {"medium", "high"}
```

- [ ] **Step 2: Write causally later local resolution test**

Start from the merged register and call `write("medium-high", new_dot)`; only the new value remains visible.

- [ ] **Step 3: Write deterministic JSON-compatibility validation**
- [ ] **Step 4: Run failure**
- [ ] **Step 5: Implement `values_by_dot` + `superseded`**
- [ ] **Step 6: Run and commit**

```bash
python -m pytest -q tests/unit/test_mvregister.py
git add src/distsys/crdt tests/unit/test_mvregister.py
git commit -m "feat: add multi value register crdt"
```

### Task 5: StoredCrdtEntry

**Files:**
- Create: `src/distsys/storage/__init__.py`
- Create: `src/distsys/storage/models.py`
- Test: `tests/unit/test_crdt_store.py`

**Interfaces:**
- Immutable `StoredCrdtEntry(key, crdt_type, state, state_version, causal_context)`

- [ ] **Step 1: Write empty-key rejection test**
- [ ] **Step 2: Write concrete-state/type mismatch test**
- [ ] **Step 3: Run failure**
- [ ] **Step 4: Implement explicit state/type validation**
- [ ] **Step 5: Run focused tests**

### Task 6: CrdtStore

**Files:**
- Create: `src/distsys/storage/crdt_store.py`
- Test: `tests/unit/test_crdt_store.py`

**Interfaces:**
- `async get(key)`
- `async snapshot(key)`
- `async put_if_absent(entry)`
- `async replace(entry, expected_type=None)`
- `async merge_entry(incoming)`
- `async keys()`
- `async snapshot_all(limit=None)`
- `key_lock(key)` async context manager

- [ ] **Step 1: Write merge test**

Merge must:
- reject different CRDT types,
- merge concrete CRDT state,
- merge `state_version`,
- merge `causal_context`.

- [ ] **Step 2: Write same-key lock serialization test**
- [ ] **Step 3: Write different-key concurrency test**
- [ ] **Step 4: Run failure**

```bash
python -m pytest -q tests/unit/test_crdt_store.py
```

- [ ] **Step 5: Implement metadata lock + per-key locks**

Do not hold one global lock during a full mutation.

- [ ] **Step 6: Run complete 4B suite**

```bash
python -m pytest -q \
  tests/unit/test_gcounter.py \
  tests/unit/test_pncounter.py \
  tests/unit/test_orset.py \
  tests/unit/test_mvregister.py \
  tests/unit/test_crdt_store.py
```

- [ ] **Step 7: Commit**

```bash
git add src/distsys/storage tests/unit/test_crdt_store.py
git commit -m "feat: add atomic in memory crdt store"
```
