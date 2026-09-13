# Phase 4 Causal Consistency & CRDT Replication Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver `v0.4.0`, adding causally consistent primary-less CRDT replication to the verified Phase-3 cluster.

**Architecture:** Execute four dependency-ordered plans: 4A causal metadata, 4B CRDT core/storage, 4C replication/anti-entropy, and 4D typed protocol/client/node integration. Each plan must pass its focused tests before the next begins; the final gate reruns all quality checks and the three-node smoke.

**Tech Stack:** Python 3.12+, asyncio, Protobuf, pytest, Ruff, Black, mypy, existing Phase-3 TCP/SWIM/consistent-hash stack.

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

## Plan Set

1. `2026-09-13-phase4a-causal-metadata.md`
2. `2026-09-13-phase4b-crdt-core-storage.md`
3. `2026-09-13-phase4c-replication-anti-entropy.md`
4. `2026-09-13-phase4d-protocol-integration.md`

### Task M1: Baseline and branch gate

**Files:**
- Read: `Makefile`
- Read: `pyproject.toml`
- Read: `src/distsys/node.py`
- Read: `src/distsys/cluster/`
- Read: `src/distsys/utils/config.py`

**Interfaces:**
- Consumes: verified `v0.3.0`
- Produces: clean `phase/4-causal-crdt` workspace

- [ ] **Step 1: Create/switch branch**

```bash
git switch main
git pull --ff-only
git switch -c phase/4-causal-crdt
```

If it already exists:

```bash
git switch phase/4-causal-crdt
git rebase main
```

- [ ] **Step 2: Verify ancestry and cleanliness**

```bash
git merge-base --is-ancestor v0.3.0 HEAD
git show -s --format='%H %s' v0.3.0^{}
git status --short
```

Expected: ancestry command exits 0; working tree is clean.

- [ ] **Step 3: Run untouched Phase-3 gate**

```bash
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
```

Expected: all existing tests/lint/type/compile checks pass.

### Task M2: Execute Phase 4A

**Files:**
- Plan: `docs/superpowers/plans/2026-09-13-phase4a-causal-metadata.md`

**Interfaces:**
- Produces: `CausalActor`, `Dot`, `VersionVector`, `CausalToken`, `CausalClock`

- [ ] **Step 1: Execute every 4A task**
- [ ] **Step 2: Run focused gate**

```bash
python -m pytest -q \
  tests/unit/test_causal_actor.py \
  tests/unit/test_dot.py \
  tests/unit/test_version_vector.py \
  tests/unit/test_causal_token.py \
  tests/unit/test_causal_clock.py
```

Expected: PASS.

### Task M3: Execute Phase 4B

**Files:**
- Plan: `docs/superpowers/plans/2026-09-13-phase4b-crdt-core-storage.md`

**Interfaces:**
- Produces: `GCounter`, `PNCounter`, `ORSet`, `MVRegister`, `CrdtStore`

- [ ] **Step 1: Execute every 4B task**
- [ ] **Step 2: Run focused gate**

```bash
python -m pytest -q \
  tests/unit/test_gcounter.py \
  tests/unit/test_pncounter.py \
  tests/unit/test_orset.py \
  tests/unit/test_mvregister.py \
  tests/unit/test_crdt_store.py
```

Expected: PASS.

### Task M4: Execute Phase 4C

**Files:**
- Plan: `docs/superpowers/plans/2026-09-13-phase4c-replication-anti-entropy.md`

**Interfaces:**
- Produces: replica selection, coalescing outbox, async state replication, targeted causal repair, digest anti-entropy

- [ ] **Step 1: Execute every 4C task**
- [ ] **Step 2: Run focused gate**

```bash
python -m pytest -q \
  tests/unit/test_replica_selector.py \
  tests/unit/test_replication_outbox.py \
  tests/unit/test_replicator.py \
  tests/unit/test_causal_repair.py \
  tests/unit/test_digest.py \
  tests/unit/test_anti_entropy.py
```

Expected: PASS.

### Task M5: Execute Phase 4D

**Files:**
- Plan: `docs/superpowers/plans/2026-09-13-phase4d-protocol-integration.md`

**Interfaces:**
- Produces: Protobuf schema/codecs, `CrdtClient`, node integration, integration tests, Phase-4 smoke

- [ ] **Step 1: Execute every 4D task**
- [ ] **Step 2: Regenerate Protobuf**

```bash
make proto
```

Expected: success.

### Task M6: Final release-candidate gate

**Files:**
- Verify: entire repository

**Interfaces:**
- Produces: evidence that the branch is ready for PR/merge, not yet a tag

- [ ] **Step 1: Run full quality**

```bash
make quality
```

Expected: pytest, Ruff, Black, and mypy all pass.

- [ ] **Step 2: Run compileall**

```bash
PYTHONPATH=src python -m compileall -q src scripts tests
```

Expected: exit 0.

- [ ] **Step 3: Run normal cluster smoke**

Terminal 1:

```bash
make phase4-cluster
```

Terminal 2:

```bash
make phase4-smoke
```

Expected: membership converges; CRDT write/read/repair/replication/convergence succeed.

- [ ] **Step 4: Run managed failure/rejoin smoke**

```bash
python scripts/phase4_smoke.py \
  --host 127.0.0.1 \
  --ports 18000 18001 18002 \
  --managed-command 'bash scripts/run_phase4_cluster.sh'
```

Expected: reduced-RF write succeeds, restarted node gets a new actor epoch, anti-entropy reconstructs its assigned state.

- [ ] **Step 5: Check compatibility-critical numeric values**

```bash
grep -nE 'REQUEST = 1|FORWARDED_REQUEST = 11|CRDT_MUTATE_REQUEST = 12' src/distsys/protocol/message.py
grep -nE 'PEER_UNAVAILABLE = 8|CAUSAL_UNAVAILABLE = 9|REPLICATION_BACKPRESSURE = 10|KEY_NOT_FOUND = 11' proto/messages.proto
```

- [ ] **Step 6: Review diff**

```bash
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors.

- [ ] **Step 7: Push branch**

```bash
git push -u origin phase/4-causal-crdt
```

Do not create `v0.4.0` until the PR is merged and the complete quality/smoke gate is rerun on merged `main`.
