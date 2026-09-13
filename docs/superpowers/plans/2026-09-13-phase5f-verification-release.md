# Phase 5F Full Verification & Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the complete secure-persistent cluster, document its guarantees precisely, and prepare a clean `v0.5.0` release candidate.

**Architecture:** Build laptop-safe local launchers around one etcd container, three TLS nodes, separate SQLite DBs, and generated development certificates. Verification covers persistence/restart, mTLS rejection, etcd outage/recovery, Phase-1–4 regressions, quality tooling, cleanup, and release metadata.

**Tech Stack:** Bash, Python 3.12, Docker Compose, OpenSSL, pytest, Ruff, Black, mypy, Protobuf compiler, Git.

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
scripts/run_phase5_cluster.sh
scripts/phase5_smoke.py
scripts/phase5_restart_smoke.py
scripts/phase5_etcd_smoke.py

docs/PHASE5_FILE_MANIFEST.md
docs/PHASE5_VERIFICATION.md
```

Modify:

```text
Makefile
README.md
docs/PHASES.md
pyproject.toml
.env.example
.gitignore
```

Final integration coverage includes all 5A–5E tests.

### Task 1: Phase-5 cluster launcher

**Files:**
- Create: `scripts/run_phase5_cluster.sh`
- Modify: `Makefile`

**Interfaces:**
- `make phase5-cluster`
- Starts:
  - etcd compose service,
  - three nodes on 18000/18001/18002,
  - per-node SQLite files,
  - TLS/mTLS,
  - conservative `CPU_WORKERS=1`.
- Owns PID/log directories and only kills processes it launched.

- [ ] **Step 1: Add preflight checks**

Fail before launch if:
- required ports occupied,
- Docker unavailable,
- certificates missing,
- a prior Phase-5 PID file identifies live owned processes.

- [ ] **Step 2: Configure each node**

Example node-0 environment:

```text
NODE_ID=node-0
NODE_PORT=18000
CLUSTER_ENABLED=true
CRDT_ENABLED=true
PERSISTENCE_ENABLED=true
PERSISTENCE_DB_PATH=<runtime>/node-0.db
ETCD_ENABLED=true
TLS_ENABLED=true
MTLS_REQUIRED=true
TLS_CA_FILE=.../ca.crt
TLS_CERT_FILE=.../node-0/node.crt
TLS_KEY_FILE=.../node-0/node.key
CPU_WORKERS=1
```

- [ ] **Step 3: Add trap cleanup**
- [ ] **Step 4: Run manually and verify all three ports listen**
- [ ] **Step 5: Ctrl+C and verify ports become free**
- [ ] **Step 6: Commit**

```bash
git add scripts/run_phase5_cluster.sh Makefile
git commit -m "test: add secure persistent phase five cluster launcher"
```

### Task 2: Normal secure persistence smoke

**Files:**
- Create: `scripts/phase5_smoke.py`
- Modify: `Makefile`

**Interfaces:**
- `make phase5-smoke`
- `make phase5-secure-smoke` can orchestrate certs + cluster + all smokes.

- [ ] **Step 1: Connect CrdtClient using trusted CA and development client certificate**
- [ ] **Step 2: Verify membership convergence**
- [ ] **Step 3: Exercise GCounter, PNCounter, ORSet, MVRegister**
- [ ] **Step 4: Verify each node DB exists and schema version is 1**
- [ ] **Step 5: Verify TLS peer operation succeeds**
- [ ] **Step 6: Print deterministic markers**

```text
phase5_mtls_cluster=PASS
phase5_durable_crdts=PASS
phase5_schema_v1=PASS
```

- [ ] **Step 7: Run**
- [ ] **Step 8: Commit**

```bash
git add scripts/phase5_smoke.py Makefile
git commit -m "test: add phase five secure persistence smoke"
```

### Task 3: Managed restart smoke

**Files:**
- Create: `scripts/phase5_restart_smoke.py`

**Interfaces:**
- Operates only on cluster processes launched by Phase-5 launcher.

- [ ] **Step 1: Write state before failure**
- [ ] **Step 2: Capture node-2 SWIM incarnation and durable causal actor**
- [ ] **Step 3: Stop node-2**
- [ ] **Step 4: Continue mutations on remaining replicas**
- [ ] **Step 5: Restart node-2 using same DB/cert**
- [ ] **Step 6: Verify**
  - new SWIM incarnation,
  - same durable causal actor,
  - counter non-regression,
  - recovered/reconciled state,
  - state persists after second reopen.
- [ ] **Step 7: Print markers**

```text
phase5_restart_durable_state=PASS
phase5_restart_new_swim_epoch=PASS
phase5_restart_same_causal_actor=PASS
phase5_restart_reconciliation=PASS
```

- [ ] **Step 8: Commit**

```bash
git add scripts/phase5_restart_smoke.py
git commit -m "test: add phase five restart recovery smoke"
```

### Task 4: etcd outage/recovery smoke

**Files:**
- Create: `scripts/phase5_etcd_smoke.py`

**Interfaces:**
- Stops/restarts only the compose etcd service used by the local Phase-5 cluster.

- [ ] **Step 1: Verify coordination healthy**
- [ ] **Step 2: Stop etcd**
- [ ] **Step 3: Wait for coordination degraded**
- [ ] **Step 4: Perform CRDT write/read successfully**
- [ ] **Step 5: Restart etcd**
- [ ] **Step 6: Verify member registrations return**
- [ ] **Step 7: Print**

```text
phase5_etcd_degraded_data_plane=PASS
phase5_etcd_registration_recovered=PASS
```

- [ ] **Step 8: Commit**

```bash
git add scripts/phase5_etcd_smoke.py
git commit -m "test: add phase five etcd recovery smoke"
```

### Task 5: Bad certificate and plaintext smoke checks

**Files:**
- Expand: `scripts/phase5_smoke.py`

**Interfaces:**
- Uses wrong CA context, wrong-node cert, and raw plaintext socket.

- [ ] **Step 1: Unknown CA handshake must fail**
- [ ] **Step 2: Wrong logical node certificate for a peer message must fail**
- [ ] **Step 3: Plain TCP frame to TLS listener must not produce valid protocol response**
- [ ] **Step 4: Print**

```text
phase5_unknown_ca_rejected=PASS
phase5_wrong_node_identity_rejected=PASS
phase5_plaintext_rejected=PASS
```

- [ ] **Step 5: Commit**

```bash
git add scripts/phase5_smoke.py
git commit -m "test: add phase five tls negative smoke checks"
```

### Task 6: Full Makefile workflow

**Files:**
- Modify: `Makefile`

**Interfaces:**
Add phony targets:

```make
phase5-certs:
	bash scripts/generate_dev_certs.sh

phase5-etcd-up:
	docker compose -f docker/etcd/docker-compose.yml up -d

phase5-etcd-down:
	docker compose -f docker/etcd/docker-compose.yml down

phase5-cluster:
	bash scripts/run_phase5_cluster.sh

phase5-smoke:
	$(PYTHON) scripts/phase5_smoke.py --host 127.0.0.1 --ports 18000 18001 18002

phase5-restart-smoke:
	$(PYTHON) scripts/phase5_restart_smoke.py

phase5-etcd-smoke:
	$(PYTHON) scripts/phase5_etcd_smoke.py
```

`phase5-secure-smoke` runs the intended local end-to-end sequence and ensures cleanup on failure.

- [ ] **Step 1: Add targets**
- [ ] **Step 2: Run each target separately**
- [ ] **Step 3: Run aggregate target**
- [ ] **Step 4: Commit**

### Task 7: Documentation and package version

**Files:**
- Modify: `README.md`
- Modify: `docs/PHASES.md`
- Create: `docs/PHASE5_FILE_MANIFEST.md`
- Create: `docs/PHASE5_VERIFICATION.md`
- Modify: `pyproject.toml`

**Interfaces:**
- Package version becomes `0.5.0` only when all feature work is complete.
- README states:
  - local durable ACK,
  - no quorum durability,
  - etcd coordination only,
  - SWIM live membership,
  - volatile replication outbox,
  - no exactly-once claim,
  - TLS secure profile and dev-cert warning.

- [ ] **Step 1: Update project metadata**

```toml
version = "0.5.0"
description = "Phase 5: secure persistence, restart recovery, etcd coordination, and mTLS"
```

- [ ] **Step 2: Document architecture/runbook**
- [ ] **Step 3: Add file manifest grouped by subsystem**
- [ ] **Step 4: Add verification document with exact commands and expected markers**
- [ ] **Step 5: Commit**

```bash
git add README.md docs pyproject.toml
git commit -m "docs: document phase five secure persistence"
```

### Task 8: Complete regression and quality gate

**Files:**
- Verify entire repository

**Interfaces:**
- Release evidence.

- [ ] **Step 1: Regenerate Protobuf**

```bash
make proto
```

- [ ] **Step 2: Format**

```bash
python -m black src tests scripts
python -m ruff check --fix src tests scripts
python -m black src tests scripts
```

- [ ] **Step 3: Run complete quality**

```bash
make quality
```

Expected:
- all pytest tests pass,
- Ruff zero errors,
- Black no changes,
- mypy zero errors.

- [ ] **Step 4: Compile**

```bash
PYTHONPATH=src python -m compileall -q src scripts tests
```

Expected: exit 0.

- [ ] **Step 5: Re-run Phase-4 smoke in compatibility/plaintext profile**

```bash
make phase4-cluster
```

In another terminal:

```bash
make phase4-smoke
```

Expected: Phase-4 smoke still passes.

### Task 9: Full secure system verification

**Files:**
- Verify scripts/integration environment

**Interfaces:**
- Proves complete Phase-5 exit gate.

- [ ] **Step 1: Generate clean cert set**

```bash
rm -rf certs/generated
make phase5-certs
```

- [ ] **Step 2: Run aggregate secure smoke**

```bash
make phase5-secure-smoke
```

Expected markers include:

```text
phase5_mtls_cluster=PASS
phase5_durable_crdts=PASS
phase5_restart_durable_state=PASS
phase5_restart_same_causal_actor=PASS
phase5_restart_reconciliation=PASS
phase5_etcd_degraded_data_plane=PASS
phase5_etcd_registration_recovered=PASS
phase5_unknown_ca_rejected=PASS
phase5_wrong_node_identity_rejected=PASS
phase5_plaintext_rejected=PASS
PHASE5_SMOKE=PASS
```

- [ ] **Step 3: Verify cleanup**

```bash
for port in 18000 18001 18002 2379; do
  ss -ltnp | grep ":$port" || echo "Port $port is free"
done
```

Expected: application ports free after managed smoke; etcd 2379 free after aggregate teardown.

### Task 10: Secret/data hygiene and release-candidate commit review

**Files:**
- Verify Git index/worktree

**Interfaces:**
- No private runtime state committed.

- [ ] **Step 1: Check tracked sensitive files**

```bash
if git ls-files | grep -E '(\.key$|certs/generated|\.db$|\.db-wal$|\.db-shm$)'; then
  echo "Sensitive/runtime artifact is tracked"
  exit 1
fi
```

- [ ] **Step 2: Review branch diff**

```bash
git diff --check v0.4.0..HEAD
git diff --stat v0.4.0..HEAD
git log --oneline --decorate v0.4.0..HEAD
git status --short
```

Expected: clean working tree and no whitespace errors.

- [ ] **Step 3: Push branch**

```bash
git push -u origin phase/5-secure-persistence
```

Do not create the release tag on the feature branch.

### Task 11: Post-merge release procedure

**Files:**
- No new implementation changes.

**Interfaces:**
- Creates final annotated `v0.5.0` only after merged-main verification.

- [ ] **Step 1: Merge through reviewed PR**
- [ ] **Step 2: Synchronize main**

```bash
git switch main
git pull --ff-only
git fetch --prune --tags
```

- [ ] **Step 3: Re-run final gates on merged main**

```bash
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
make phase5-secure-smoke
```

- [ ] **Step 4: Create annotated tag**

```bash
git tag -a v0.5.0 -m "Phase 5: Secure Persistence & Recovery"
git push origin main
git push origin v0.5.0
```

- [ ] **Step 5: Verify remote release identity**

```bash
git ls-remote origin refs/heads/main refs/tags/v0.5.0 refs/tags/v0.5.0^{}
```

Required invariant:

```text
origin/main commit == v0.5.0^{} commit
```
