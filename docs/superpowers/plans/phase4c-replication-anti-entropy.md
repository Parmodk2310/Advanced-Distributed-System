# Phase 4C Replication and Anti-Entropy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement consistent-hash replica selection, a bounded generation-safe coalescing outbox, async state replication, targeted causal repair, and digest-driven anti-entropy.

**Architecture:** Replica selection wraps the existing Phase-3 ring. Writes reserve replication responsibility before mutation. Fast replication sends full per-key CRDT state; causal repair actively fetches missing frontier; digest anti-entropy repairs long-lived divergence.

**Tech Stack:** Python 3.12+, asyncio, Phase-3 ring/deadline/retry components, Phase-4 causal/CRDT/store modules, pytest.

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
src/distsys/replication/
├── __init__.py
├── replica_selector.py
├── outbox.py
├── replicator.py
├── causal_repair.py
├── digest.py
├── anti_entropy.py
└── service.py
```

### Task 1: ReplicaSelector

**Files:**
- Create: `src/distsys/replication/__init__.py`
- Create: `src/distsys/replication/replica_selector.py`
- Test: `tests/unit/test_replica_selector.py`

**Interfaces:**
- `replicas(key) -> tuple[ClusterMember, ...]`
- `is_replica(node_id, key) -> bool`
- `first_remote_replica(local_node_id, key) -> ClusterMember | None`

- [ ] **Step 1: Write tests that compare output directly with `ring.candidates(key)`**
- [ ] **Step 2: Test RF contraction when fewer ALIVE nodes exist**
- [ ] **Step 3: Run failure**
- [ ] **Step 4: Implement thin wrapper; do not duplicate hashing**
- [ ] **Step 5: Run and commit**

```bash
python -m pytest -q tests/unit/test_replica_selector.py
git add src/distsys/replication tests/unit/test_replica_selector.py
git commit -m "feat: add crdt replica selection"
```

### Task 2: Bounded coalescing outbox

**Files:**
- Create: `src/distsys/replication/outbox.py`
- Test: `tests/unit/test_replication_outbox.py`

**Interfaces:**
- `ReplicationBackpressureError`
- `OutboxReservation`
- `PendingReplication(peer_node_id, key, generation, state)`
- `reserve(pairs)`
- `publish(reservation, states_by_key)`
- `next_ready()`
- `complete(peer_node_id, key, sent_generation)`
- `abandon(peer_node_id, key, sent_generation)`
- `pending_count()`

- [ ] **Step 1: Test one new pair consumes one slot**
- [ ] **Step 2: Test full outbox rejects an additional new pair**
- [ ] **Step 3: Test already-pending pair coalesces without extra capacity**
- [ ] **Step 4: Test all-or-nothing multi-peer reservation**
- [ ] **Step 5: Test generation race**

```text
publish generation 1
worker takes generation 1
publish generation 2
complete generation 1
pair must remain pending
worker receives generation 2
```

- [ ] **Step 6: Run failure**
- [ ] **Step 7: Implement atomic reservation and generation bookkeeping**
- [ ] **Step 8: Run and commit**

```bash
python -m pytest -q tests/unit/test_replication_outbox.py
git add src/distsys/replication/outbox.py tests/unit/test_replication_outbox.py
git commit -m "feat: add coalescing replication outbox"
```

### Task 3: Replicator

**Files:**
- Create: `src/distsys/replication/replicator.py`
- Test: `tests/unit/test_replicator.py`

**Interfaces:**
- `ReplicationPeerTransport.send_state(peer_node_id, state)`
- `Replicator.start()`
- `Replicator.stop()`

- [ ] **Step 1: Create fake transport recording sends**
- [ ] **Step 2: Test successful send clears matching generation**
- [ ] **Step 3: Test transport failures receive bounded retry**
- [ ] **Step 4: Test retry exhaustion stops fast-path retry**
- [ ] **Step 5: Test generation update during in-flight send schedules latest state**
- [ ] **Step 6: Run failure**
- [ ] **Step 7: Implement worker lifecycle and injected retry policy**
- [ ] **Step 8: Run and commit**

```bash
python -m pytest -q tests/unit/test_replicator.py
git add src/distsys/replication/replicator.py tests/unit/test_replicator.py
git commit -m "feat: add asynchronous crdt replicator"
```

### Task 4: CausalRepairService

**Files:**
- Create: `src/distsys/replication/causal_repair.py`
- Test: `tests/unit/test_causal_repair.py`

**Interfaces:**
- `CausalUnavailableError`
- `CausalRepairResult(satisfied, merged_version, contacted_nodes, successful_nodes)`
- `CausalRepairPeer.fetch_state(peer, key, deadline)`
- `ensure(key, required, deadline)`

- [ ] **Step 1: Test local causal fast path contacts no peer**
- [ ] **Step 2: Test remote fetches start in parallel using asyncio Events**
- [ ] **Step 3: Test peer state merge satisfies required token**
- [ ] **Step 4: Test peer causal proof can advance context**
- [ ] **Step 5: Test unsatisfied frontier raises `CausalUnavailableError`**
- [ ] **Step 6: Verify same `Deadline` instance is passed to all peer calls**
- [ ] **Step 7: Run failure**
- [ ] **Step 8: Implement and run**

```bash
python -m pytest -q tests/unit/test_causal_repair.py
```

- [ ] **Step 9: Commit**

```bash
git add src/distsys/replication/causal_repair.py tests/unit/test_causal_repair.py
git commit -m "feat: add targeted causal repair"
```

### Task 5: Digest model

**Files:**
- Create: `src/distsys/replication/digest.py`
- Test: `tests/unit/test_digest.py`

**Interfaces:**
- `CrdtDigestEntry`
- `DigestRelation`: EQUAL, LOCAL_AHEAD, REMOTE_AHEAD, CONCURRENT, METADATA_ONLY
- `compare_digest(local, remote)`

- [ ] **Step 1: Write one test for each relation**
- [ ] **Step 2: Run failure**
- [ ] **Step 3: Implement using `state_version` first; equal state + differing context => METADATA_ONLY**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/test_digest.py
git add src/distsys/replication/digest.py tests/unit/test_digest.py
git commit -m "feat: add anti entropy causal digests"
```

### Task 6: AntiEntropyService

**Files:**
- Create: `src/distsys/replication/anti_entropy.py`
- Test: `tests/unit/test_anti_entropy.py`

**Interfaces:**
- Peer protocol: `exchange_digest`, `fetch_state`, `send_state`, `send_metadata`
- `run_once`, `start`, `stop`

- [ ] **Step 1: Test equal digest causes no full-state transfer**
- [ ] **Step 2: Test remote-ahead fetch + local merge**
- [ ] **Step 3: Test local-ahead peer repair**
- [ ] **Step 4: Test concurrent fetch + merge + peer repair**
- [ ] **Step 5: Test metadata-only repair without full state**
- [ ] **Step 6: Test batch-size cap**
- [ ] **Step 7: Test one relevant peer per cycle**
- [ ] **Step 8: Run failure**
- [ ] **Step 9: Implement with injectable peer chooser/RNG**
- [ ] **Step 10: Run and commit**

```bash
python -m pytest -q tests/unit/test_anti_entropy.py
git add src/distsys/replication/anti_entropy.py tests/unit/test_anti_entropy.py
git commit -m "feat: add digest driven anti entropy"
```

### Task 7: ReplicationService facade

**Files:**
- Create: `src/distsys/replication/service.py`
- Test: extend 4C unit files

**Interfaces:**
- `start`, `stop`
- `reserve_write`
- `publish_write`
- `merge_replica_state`
- `ensure_causal`
- `digest_snapshot`
- `merge_metadata`

- [ ] **Step 1: Test clean start/stop of all background tasks**
- [ ] **Step 2: Test reserve/publish delegates without duplicating logic**
- [ ] **Step 3: Implement facade**
- [ ] **Step 4: Run full 4C suite**

```bash
python -m pytest -q \
  tests/unit/test_replica_selector.py \
  tests/unit/test_replication_outbox.py \
  tests/unit/test_replicator.py \
  tests/unit/test_causal_repair.py \
  tests/unit/test_digest.py \
  tests/unit/test_anti_entropy.py
```

- [ ] **Step 5: Commit**

```bash
git add src/distsys/replication tests/unit
git commit -m "feat: coordinate crdt replication services"
```
