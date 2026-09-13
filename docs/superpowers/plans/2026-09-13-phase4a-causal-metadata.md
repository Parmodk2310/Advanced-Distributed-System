# Phase 4A Causal Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement incarnation-scoped causal identity, dotted mutations, version-vector ordering, session tokens, and a concurrency-safe local causal clock.

**Architecture:** All causal types are networking-independent immutable domain objects. The actor includes Phase-3 incarnation so a restarted node can restart its local counter without reusing an old Dot identity.

**Tech Stack:** Python 3.12+, dataclasses, asyncio, pytest.

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
src/distsys/causal/
├── __init__.py
├── actor.py
├── dot.py
├── version_vector.py
├── token.py
└── clock.py

tests/unit/
├── test_causal_actor.py
├── test_dot.py
├── test_version_vector.py
├── test_causal_token.py
└── test_causal_clock.py
```

### Task 1: CausalActor and Dot

**Files:**
- Create: `src/distsys/causal/__init__.py`
- Create: `src/distsys/causal/actor.py`
- Create: `src/distsys/causal/dot.py`
- Test: `tests/unit/test_causal_actor.py`
- Test: `tests/unit/test_dot.py`

**Interfaces:**
- Produces `CausalActor(node_id: str, incarnation: int)` and `Dot(actor: CausalActor, counter: int)`
- `CausalActor.wire_key() -> str`
- Both are immutable/orderable/slotted

- [ ] **Step 1: Write failing tests**

```python
import pytest
from distsys.causal.actor import CausalActor
from distsys.causal.dot import Dot

def test_actor_identity_includes_incarnation():
    assert CausalActor("node-1", 10) != CausalActor("node-1", 11)

def test_actor_wire_key():
    assert CausalActor("node-1", 10).wire_key() == "node-1@10"

def test_actor_validation():
    with pytest.raises(ValueError):
        CausalActor("", 1)
    with pytest.raises(ValueError):
        CausalActor("node-1", -1)

def test_dot_validation():
    actor = CausalActor("node-1", 10)
    with pytest.raises(ValueError):
        Dot(actor, 0)
    assert Dot(actor, 1).counter == 1
```

- [ ] **Step 2: Run and confirm failure**

```bash
python -m pytest -q tests/unit/test_causal_actor.py tests/unit/test_dot.py
```

- [ ] **Step 3: Implement minimal domain types**

```python
@dataclass(frozen=True, order=True, slots=True)
class CausalActor:
    node_id: str
    incarnation: int

    def wire_key(self) -> str:
        return f"{self.node_id}@{self.incarnation}"

@dataclass(frozen=True, order=True, slots=True)
class Dot:
    actor: CausalActor
    counter: int
```

Add explicit validation in `__post_init__`.

- [ ] **Step 4: Run tests**
- [ ] **Step 5: Commit**

```bash
git add src/distsys/causal tests/unit/test_causal_actor.py tests/unit/test_dot.py
git commit -m "feat: add incarnation scoped causal identity"
```

### Task 2: VersionVector

**Files:**
- Create: `src/distsys/causal/version_vector.py`
- Modify: `src/distsys/causal/__init__.py`
- Test: `tests/unit/test_version_vector.py`

**Interfaces:**
- Produces `VersionRelation`: BEFORE, AFTER, EQUAL, CONCURRENT
- Produces immutable `VersionVector`
- Methods: `get`, `items`, `with_dot`, `merge`, `compare`, `dominates`, `concurrent_with`, `missing_from`

- [ ] **Step 1: Write failing partial-order tests**

```python
def test_partial_order():
    a0 = CausalActor("node-0", 1)
    a1 = CausalActor("node-1", 1)
    before = VersionVector({a0: 3, a1: 2})
    after = VersionVector({a0: 4, a1: 2})
    concurrent = VersionVector({a0: 2, a1: 3})
    assert before.compare(after) is VersionRelation.BEFORE
    assert after.compare(before) is VersionRelation.AFTER
    assert after.compare(after) is VersionRelation.EQUAL
    assert after.compare(concurrent) is VersionRelation.CONCURRENT
```

- [ ] **Step 2: Write failing merge/missing tests**

```python
def test_merge_and_missing_frontier():
    a0 = CausalActor("node-0", 1)
    a1 = CausalActor("node-1", 1)
    left = VersionVector({a0: 5, a1: 2})
    right = VersionVector({a0: 3, a1: 4})
    assert left.merge(right) == VersionVector({a0: 5, a1: 4})
    assert VersionVector({a0: 6}).missing_from(VersionVector({a0: 8})) == {
        a0: (7, 8)
    }
```

- [ ] **Step 3: Run failure**

```bash
python -m pytest -q tests/unit/test_version_vector.py
```

- [ ] **Step 4: Implement deterministic immutable normalization**

Reject negative counters. Omit zero entries. Sort by `CausalActor`.

- [ ] **Step 5: Implement relation and merge logic**
- [ ] **Step 6: Add CRDT-style algebra checks for vector merge**

```python
assert a.merge(b) == b.merge(a)
assert a.merge(b).merge(c) == a.merge(b.merge(c))
assert a.merge(a) == a
```

- [ ] **Step 7: Run and commit**

```bash
python -m pytest -q tests/unit/test_version_vector.py
git add src/distsys/causal tests/unit/test_version_vector.py
git commit -m "feat: add causal version vectors"
```

### Task 3: CausalToken

**Files:**
- Create: `src/distsys/causal/token.py`
- Test: `tests/unit/test_causal_token.py`

**Interfaces:**
- Produces immutable `CausalToken(version: VersionVector)`
- Methods: `empty`, `merge`

- [ ] **Step 1: Write failing tests**

```python
def test_empty_and_merge():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    assert CausalToken.empty().version == VersionVector()
    merged = CausalToken(VersionVector({a: 2})).merge(
        CausalToken(VersionVector({b: 4}))
    )
    assert merged.version == VersionVector({a: 2, b: 4})
```

- [ ] **Step 2: Run failure**
- [ ] **Step 3: Implement frozen/slotted token**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/test_causal_token.py
git add src/distsys/causal tests/unit/test_causal_token.py
git commit -m "feat: add session causal tokens"
```

### Task 4: CausalClock

**Files:**
- Create: `src/distsys/causal/clock.py`
- Test: `tests/unit/test_causal_clock.py`

**Interfaces:**
- `CausalClock(actor)`
- `async observe(version) -> VersionVector`
- `async allocate(observed: VersionVector | None = None) -> tuple[Dot, VersionVector]`
- `async frontier() -> VersionVector`

- [ ] **Step 1: Write failing async tests**

```python
@pytest.mark.asyncio
async def test_counter_increases():
    actor = CausalActor("node-0", 100)
    clock = CausalClock(actor)
    d1, _ = await clock.allocate()
    d2, frontier = await clock.allocate()
    assert (d1.counter, d2.counter) == (1, 2)
    assert frontier.get(actor) == 2

@pytest.mark.asyncio
async def test_new_incarnation_prevents_dot_collision():
    old = CausalClock(CausalActor("node-0", 100))
    new = CausalClock(CausalActor("node-0", 101))
    old_dot, _ = await old.allocate()
    new_dot, _ = await new.allocate()
    assert old_dot != new_dot
```

- [ ] **Step 2: Run failure**

```bash
python -m pytest -q tests/unit/test_causal_clock.py
```

- [ ] **Step 3: Implement with `asyncio.Lock`**

Allocate merges observed frontier first, increments only the local actor component, and returns the new Dot plus updated frontier.

- [ ] **Step 4: Run complete 4A suite**

```bash
python -m pytest -q \
  tests/unit/test_causal_actor.py \
  tests/unit/test_dot.py \
  tests/unit/test_version_vector.py \
  tests/unit/test_causal_token.py \
  tests/unit/test_causal_clock.py
```

- [ ] **Step 5: Commit**

```bash
git add src/distsys/causal tests/unit/test_causal_clock.py
git commit -m "feat: add local causal clock"
```
