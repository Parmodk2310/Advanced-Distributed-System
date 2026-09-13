# Phase 5 Secure Persistence & Recovery Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver `v0.5.0` with locally durable causal CRDT mutations, deterministic restart recovery, etcd lease/discovery coordination, and TLS 1.3 mutual authentication.

**Architecture:** Execute six dependency-ordered workstreams. 5A establishes durable storage primitives; 5B integrates durability into the Phase-4 CRDT path; 5C adds etcd coordination; 5D secures all socket traffic; 5E orchestrates restore/reconciliation/readiness; 5F proves the complete release.

**Tech Stack:** Python 3.12+, asyncio, sqlite3/WAL, Protobuf, etcd3gw 2.7.x, TLS 1.3/mTLS via Python ssl, pytest, Ruff, Black, mypy, Docker etcd for integration.

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

## Plan Set and Dependency Order

```text
v0.4.0
  │
  ▼
5A Durable Persistence Foundation
  │
  ▼
5B Durable CRDT Integration
  │
  ├──────────────┐
  ▼              ▼
5C etcd       5D TLS/mTLS
  │              │
  └──────┬───────┘
         ▼
5E Recovery Orchestration
         │
         ▼
5F Full Verification & Release
```

Plan files:

```text
docs/superpowers/plans/
├── 2026-09-13-phase5-master.md
├── 2026-09-13-phase5a-persistence-foundation.md
├── 2026-09-13-phase5b-durable-crdt-integration.md
├── 2026-09-13-phase5c-etcd-coordination.md
├── 2026-09-13-phase5d-tls-mtls-security.md
├── 2026-09-13-phase5e-recovery-orchestration.md
└── 2026-09-13-phase5f-verification-release.md
```

### Task M1: Verify branch, spec commit, and Phase-4 baseline

**Files:**
- Read: `docs/superpowers/specs/2026-09-13-phase5-secure-persistence-design.md`
- Read: `pyproject.toml`
- Read: `src/distsys/node.py`
- Read: `src/distsys/crdt_service.py`
- Read: `src/distsys/replication/`
- Read: `src/distsys/cluster/`

**Interfaces:**
- Consumes: clean `v0.4.0` baseline plus committed Phase-5 spec
- Produces: verified branch ready for implementation

- [ ] **Step 1: Confirm branch and ancestry**

```bash
git branch --show-current
git merge-base --is-ancestor v0.4.0 HEAD
git log --oneline --decorate -3
git status --short
```

Expected:
- current branch `phase/5-secure-persistence`,
- ancestry command exits 0,
- spec commit is ahead of `v0.4.0`,
- working tree clean.

- [ ] **Step 2: Run untouched baseline quality gate**

```bash
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
```

Expected: Phase-4 suite passes with no Ruff/Black/mypy/compile errors.

### Task M2: Execute 5A — Durable Persistence Foundation

**Files:**
- Plan: `docs/superpowers/plans/2026-09-13-phase5a-persistence-foundation.md`

**Interfaces:**
- Produces:
  - deterministic persistence codec,
  - schema v1,
  - SQLite repository,
  - durable identity/clock/CRDT entries,
  - bounded persistence executor,
  - SQLite backup.

- [ ] **Step 1: Execute every 5A task in order**
- [ ] **Step 2: Run 5A focused gate**

```bash
python -m pytest -q \
  tests/unit/persistence/test_models.py \
  tests/unit/persistence/test_codec.py \
  tests/unit/persistence/test_executor.py \
  tests/unit/persistence/test_migrations.py \
  tests/unit/persistence/test_sqlite_repository.py \
  tests/unit/persistence/test_backup.py
```

Expected: PASS.

### Task M3: Execute 5B — Durable CRDT Integration

**Files:**
- Plan: `docs/superpowers/plans/2026-09-13-phase5b-durable-crdt-integration.md`

**Interfaces:**
- Produces:
  - staged causal allocation,
  - durable CRDT state adapter,
  - local commit-before-ACK,
  - durable replica/repair/anti-entropy merge,
  - persistence error mapping.

- [ ] **Step 1: Execute every 5B task in order**
- [ ] **Step 2: Run 5A+5B focused gate**

```bash
python -m pytest -q \
  tests/unit/test_causal_clock.py \
  tests/unit/persistence \
  tests/integration/test_durable_crdt_restart.py \
  tests/integration/test_durable_causal_clock.py \
  tests/integration/test_persistence_backpressure.py \
  tests/integration/test_durable_replica_merge.py
```

Expected: PASS.

### Task M4: Execute 5C — etcd Coordination

**Files:**
- Plan: `docs/superpowers/plans/2026-09-13-phase5c-etcd-coordination.md`

**Interfaces:**
- Produces:
  - coordination model/protocol,
  - etcd3gw adapter,
  - leases,
  - discovery,
  - degraded/recovery behavior.

- [ ] **Step 1: Execute every 5C task**
- [ ] **Step 2: Run coordination unit gate**

```bash
python -m pytest -q tests/unit/coordination
```

Expected: PASS without requiring a live etcd daemon.

- [ ] **Step 3: Start integration etcd**

```bash
docker compose -f docker/etcd/docker-compose.yml up -d
docker compose -f docker/etcd/docker-compose.yml ps
```

Expected: one healthy etcd service on `127.0.0.1:2379`.

- [ ] **Step 4: Run etcd integration gate**

```bash
python -m pytest -q \
  tests/integration/test_etcd_registration.py \
  tests/integration/test_etcd_lease_expiry.py \
  tests/integration/test_etcd_outage.py
```

Expected: PASS.

### Task M5: Execute 5D — TLS/mTLS Security

**Files:**
- Plan: `docs/superpowers/plans/2026-09-13-phase5d-tls-mtls-security.md`

**Interfaces:**
- Produces:
  - TLS contexts,
  - logical SAN node identity verification,
  - secure server/client/peer transports,
  - development PKI script,
  - negative TLS tests.

- [ ] **Step 1: Execute every 5D task**
- [ ] **Step 2: Generate development certificates**

```bash
bash scripts/generate_dev_certs.sh
```

Expected: generated CA plus node/client certificates under ignored `certs/generated/`.

- [ ] **Step 3: Run TLS unit/integration gate**

```bash
python -m pytest -q \
  tests/unit/security \
  tests/integration/test_mtls_valid_peer.py \
  tests/integration/test_mtls_unknown_ca.py \
  tests/integration/test_mtls_identity_mismatch.py \
  tests/integration/test_tls_plaintext_rejected.py
```

Expected: PASS.

### Task M6: Execute 5E — Recovery Orchestration

**Files:**
- Plan: `docs/superpowers/plans/2026-09-13-phase5e-recovery-orchestration.md`

**Interfaces:**
- Produces:
  - readiness/health state,
  - restore service,
  - full-pass recovery reconciliation,
  - ordered node startup/shutdown,
  - coordination degradation after READY.

- [ ] **Step 1: Execute every 5E task**
- [ ] **Step 2: Run recovery gate**

```bash
python -m pytest -q \
  tests/unit/recovery \
  tests/unit/health \
  tests/integration/test_durable_crdt_restart.py \
  tests/integration/test_replica_recovery_reconciliation.py \
  tests/integration/test_recovery_readiness.py
```

Expected: PASS.

### Task M7: Execute 5F — Full Verification & Release

**Files:**
- Plan: `docs/superpowers/plans/2026-09-13-phase5f-verification-release.md`

**Interfaces:**
- Produces: secure local cluster launchers, smokes, documentation, complete release evidence.

- [ ] **Step 1: Execute every 5F task**
- [ ] **Step 2: Run complete quality gate**

```bash
make proto
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
```

Expected: zero failures/errors.

- [ ] **Step 3: Run secure Phase-5 smoke**

```bash
make phase5-secure-smoke
```

Expected final marker:

```text
PHASE5_SMOKE=PASS
```

### Task M8: Release branch handoff

**Files:**
- Verify: repository

**Interfaces:**
- Produces: reviewed feature branch suitable for PR, not a release tag yet

- [ ] **Step 1: Verify diff hygiene**

```bash
git diff --check
git status --short
git log --oneline --decorate v0.4.0..HEAD
```

- [ ] **Step 2: Verify runtime secrets/data are untracked**

```bash
git status --ignored --short | grep -E 'certs/generated|\.db|\.db-wal|\.db-shm' || true
git ls-files | grep -E '(\.key$|certs/generated|\.db$|\.db-wal$|\.db-shm$)' && exit 1 || true
```

Expected: no private key or database tracked.

- [ ] **Step 3: Push feature branch only after all gates pass**

```bash
git push -u origin phase/5-secure-persistence
```

Do not create `v0.5.0` until review/PR merge and full post-merge verification on `main`.
