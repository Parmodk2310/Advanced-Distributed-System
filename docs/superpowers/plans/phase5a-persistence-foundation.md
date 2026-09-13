# Phase 5A Durable Persistence Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the storage primitives needed to durably encode, transact, restore, migrate, and back up Phase-4 causal CRDT state.

**Architecture:** Use deterministic canonical JSON above SQLite WAL. `SQLiteStateRepository` exposes an async repository API but executes blocking SQLite work through a bounded `PersistenceExecutor`; every call opens its own short-lived SQLite connection, avoiding cross-thread connection sharing.

**Tech Stack:** Python 3.12+, sqlite3, asyncio.to_thread, UUIDs, canonical JSON, pytest.

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
src/distsys/persistence/
├── __init__.py
├── errors.py
├── models.py
├── codec.py
├── repository.py
├── executor.py
├── migrations.py
├── sqlite_repository.py
└── backup.py
```

Create tests:

```text
tests/unit/persistence/
├── __init__.py
├── test_models.py
├── test_codec.py
├── test_executor.py
├── test_migrations.py
├── test_sqlite_repository.py
└── test_backup.py
```

Modify:

```text
src/distsys/utils/config.py
.env.example
.gitignore
```

### Task 1: Durable models and persistence exceptions

**Files:**
- Create: `src/distsys/persistence/__init__.py`
- Create: `src/distsys/persistence/errors.py`
- Create: `src/distsys/persistence/models.py`
- Test: `tests/unit/persistence/test_models.py`

**Interfaces:**
- Produces:
  - `PersistenceError`
  - `PersistenceUnavailableError`
  - `PersistenceBackpressureError`
  - `RepositoryIntegrityError`
  - `RepositorySchemaError`
  - `NodeIdentityMismatchError`
  - `DurableNodeIdentity`
  - `DurableCausalState`
  - `RepositoryHealth`

- [ ] **Step 1: Write the failing model tests**

```python
from uuid import UUID

import pytest

from distsys.causal import CausalActor, VersionVector
from distsys.persistence.models import DurableCausalState, DurableNodeIdentity

def test_durable_identity_rejects_empty_node_id():
    with pytest.raises(ValueError):
        DurableNodeIdentity(
            node_uuid=UUID("00000000-0000-0000-0000-000000000001"),
            configured_node_id="",
            causal_incarnation=1,
        )

def test_durable_causal_state_counter_matches_actor_component():
    actor = CausalActor("node-0", 500)
    state = DurableCausalState(
        actor=actor,
        local_counter=8,
        frontier=VersionVector({actor: 8}),
    )
    assert state.frontier.get(actor) == state.local_counter
```

Add one test asserting `local_counter < 0` is rejected and one asserting `frontier.get(actor) > local_counter` is rejected.

- [ ] **Step 2: Run to verify RED**

```bash
python -m pytest -q tests/unit/persistence/test_models.py
```

Expected: import failure because `distsys.persistence.models` does not exist.

- [ ] **Step 3: Implement immutable models**

Use frozen/slotted dataclasses:

```python
@dataclass(frozen=True, slots=True)
class DurableNodeIdentity:
    node_uuid: UUID
    configured_node_id: str
    causal_incarnation: int

@dataclass(frozen=True, slots=True)
class DurableCausalState:
    actor: CausalActor
    local_counter: int
    frontier: VersionVector

@dataclass(frozen=True, slots=True)
class RepositoryHealth:
    healthy: bool
    schema_version: int
    message: str = ""
```

Validation rules:
- non-empty configured node id,
- positive causal incarnation,
- non-negative local counter,
- frontier local actor component must equal `local_counter`.

- [ ] **Step 4: Run focused tests**

```bash
python -m pytest -q tests/unit/persistence/test_models.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/distsys/persistence tests/unit/persistence/test_models.py
git commit -m "feat: add durable persistence models"
```

### Task 2: Deterministic causal and CRDT durable codec

**Files:**
- Create: `src/distsys/persistence/codec.py`
- Test: `tests/unit/persistence/test_codec.py`

**Interfaces:**
- Consumes: Phase-4 causal/CRDT types
- Produces:
  - `encode_actor(actor) -> dict[str, object]`
  - `decode_actor(data) -> CausalActor`
  - `encode_version_vector(vector) -> str`
  - `decode_version_vector(raw) -> VersionVector`
  - `encode_crdt_state(state, crdt_type) -> str`
  - `decode_crdt_state(raw, crdt_type) -> CrdtState`
  - `encode_entry(entry) -> EncodedCrdtEntry`
  - `decode_entry(...) -> StoredCrdtEntry`

- [ ] **Step 1: Write failing VersionVector determinism test**

```python
def test_version_vector_encoding_is_canonical():
    a = CausalActor("node-b", 2)
    b = CausalActor("node-a", 1)
    left = VersionVector({a: 4, b: 7})
    right = VersionVector({b: 7, a: 4})
    assert encode_version_vector(left) == encode_version_vector(right)
```

- [ ] **Step 2: Write one round-trip test per CRDT**

Use exact state features:
- GCounter with two actors,
- PNCounter positive + negative,
- ORSet with active add and removed Dot,
- MVRegister with concurrent values and superseded Dot.

Each test must assert decoded object equality with the original `StoredCrdtEntry`.

- [ ] **Step 3: Write invalid JSON and unknown-type rejection tests**

```python
with pytest.raises(ValueError):
    decode_version_vector("{not-json")
```

- [ ] **Step 4: Verify RED**

```bash
python -m pytest -q tests/unit/persistence/test_codec.py
```

- [ ] **Step 5: Implement canonical JSON helper**

```python
def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
```

Encode VersionVector entries in sorted `(node_id, incarnation)` order.

- [ ] **Step 6: Implement each CRDT encoder/decoder explicitly**

Do not call pickle and do not persist Python repr strings.

- [ ] **Step 7: Run**

```bash
python -m pytest -q tests/unit/persistence/test_codec.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/distsys/persistence/codec.py tests/unit/persistence/test_codec.py
git commit -m "feat: add deterministic durable crdt codec"
```

### Task 3: Bounded PersistenceExecutor

**Files:**
- Create: `src/distsys/persistence/executor.py`
- Test: `tests/unit/persistence/test_executor.py`

**Interfaces:**
- Produces:
  - `PersistenceExecutor(capacity: int)`
  - `async run(fn: Callable[[], T], deadline: Deadline | None = None) -> T`
  - `capacity`, `in_flight`

**Behavior:**
- blocking function runs via `asyncio.to_thread`,
- admission is bounded,
- deadline exhaustion while waiting maps to `PersistenceBackpressureError`,
- exceptions raised by the blocking function propagate unchanged.

- [ ] **Step 1: Write failing capacity test**

Hold one admitted operation on an Event with capacity=1; attempt a second operation with a short `Deadline`; assert `PersistenceBackpressureError`.

- [ ] **Step 2: Write off-event-loop test**

Capture thread id in the blocking callable and assert it differs from the event-loop thread id.

- [ ] **Step 3: Verify RED**

```bash
python -m pytest -q tests/unit/persistence/test_executor.py
```

- [ ] **Step 4: Implement semaphore admission**

Use `asyncio.Semaphore(capacity)`. If a deadline exists, wrap semaphore acquisition with `asyncio.timeout(deadline.remaining())`. Release in `finally`.

- [ ] **Step 5: Run**

```bash
python -m pytest -q tests/unit/persistence/test_executor.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/distsys/persistence/executor.py tests/unit/persistence/test_executor.py
git commit -m "feat: add bounded persistence executor"
```

### Task 4: Schema v1 migration runner

**Files:**
- Create: `src/distsys/persistence/migrations.py`
- Test: `tests/unit/persistence/test_migrations.py`

**Interfaces:**
- Produces:
  - `CURRENT_SCHEMA_VERSION = 1`
  - `schema_version(conn) -> int`
  - `apply_migrations(conn) -> int`
  - ordered migration registry `{1: migration_v1}`

- [ ] **Step 1: Write new-database migration test**

Use `sqlite3.connect(":memory:")`; call `apply_migrations`; assert v1 tables exist:

```text
schema_migrations
node_identity
causal_clock
crdt_entries
```

- [ ] **Step 2: Write newer-schema rejection test**

Insert migration version 99 and assert `RepositorySchemaError`.

- [ ] **Step 3: Write idempotent reopen test**

Calling `apply_migrations` twice must leave version 1 and not duplicate rows.

- [ ] **Step 4: Verify RED**
- [ ] **Step 5: Implement v1 DDL exactly from the spec**
- [ ] **Step 6: Run**

```bash
python -m pytest -q tests/unit/persistence/test_migrations.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/distsys/persistence/migrations.py tests/unit/persistence/test_migrations.py
git commit -m "feat: add sqlite schema migration runner"
```

### Task 5: StateRepository protocol and SQLite repository open/integrity

**Files:**
- Create: `src/distsys/persistence/repository.py`
- Create: `src/distsys/persistence/sqlite_repository.py`
- Test: `tests/unit/persistence/test_sqlite_repository.py`

**Interfaces:**
- `StateRepository` protocol:
  - `open`
  - `close`
  - `integrity_check`
  - `load_identity`
  - `initialize_identity`
  - `load_clock`
  - `load_entries`
  - `commit_mutation`
  - `commit_observed_entry`
  - `mark_authority`
  - `backup`
- `SQLiteStateRepository(path, executor, busy_timeout_seconds=5.0, synchronous="NORMAL")`

- [ ] **Step 1: Write open/configuration test**

Open a temp DB then inspect with a separate connection:

```python
assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
```

- [ ] **Step 2: Write integrity-check test**

Healthy DB returns `RepositoryHealth(healthy=True, schema_version=1, ...)`.

- [ ] **Step 3: Verify RED**
- [ ] **Step 4: Implement `_connect()`**

Each blocking operation creates a short-lived `sqlite3.Connection` with:
- configured busy timeout,
- `PRAGMA foreign_keys=ON`,
- row factory `sqlite3.Row`.

`open()` sets WAL/synchronous and runs migrations through `PersistenceExecutor`.

- [ ] **Step 5: Implement `integrity_check()` using `PRAGMA quick_check`**

Anything other than `"ok"` raises `RepositoryIntegrityError`.

- [ ] **Step 6: Run**

```bash
python -m pytest -q tests/unit/persistence/test_sqlite_repository.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/distsys/persistence/repository.py src/distsys/persistence/sqlite_repository.py tests/unit/persistence/test_sqlite_repository.py
git commit -m "feat: add sqlite state repository"
```

### Task 6: Stable identity and causal clock persistence

**Files:**
- Modify: `src/distsys/persistence/sqlite_repository.py`
- Test: `tests/unit/persistence/test_sqlite_repository.py`

**Interfaces:**
- `initialize_identity(configured_node_id) -> DurableNodeIdentity`
- `load_identity() -> DurableNodeIdentity | None`
- `save_clock(state: DurableCausalState) -> None`
- `load_clock() -> DurableCausalState | None`

- [ ] **Step 1: Write identity create/reopen test**

Initialize identity, close repository object, construct a new repository on the same path, assert UUID/node-id/causal-incarnation are identical.

- [ ] **Step 2: Write identity mismatch test**

Create DB for `node-0`; call validation with configured `node-1`; assert `NodeIdentityMismatchError`.

- [ ] **Step 3: Write clock round-trip test**

Persist actor `node-0@500`, local counter 8 and a remote frontier component; reopen and assert exact equality.

- [ ] **Step 4: Implement identity with `uuid.uuid4()` and positive `time.time_ns()` causal incarnation**
- [ ] **Step 5: Implement clock upsert**
- [ ] **Step 6: Run and commit**

```bash
python -m pytest -q tests/unit/persistence/test_sqlite_repository.py
git add src/distsys/persistence/sqlite_repository.py tests/unit/persistence/test_sqlite_repository.py
git commit -m "feat: persist node identity and causal clock"
```

### Task 7: Atomic CRDT mutation persistence

**Files:**
- Modify: `src/distsys/persistence/sqlite_repository.py`
- Test: `tests/unit/persistence/test_sqlite_repository.py`

**Interfaces:**
- `commit_mutation(entry, causal_state, deadline=None) -> None`
- `load_entries() -> tuple[StoredCrdtEntry, ...]`

**Atomic transaction content:**
- causal clock upsert,
- CRDT entry upsert,
- one COMMIT.

- [ ] **Step 1: Write CRDT round-trip repository tests**

Parameterize over GCounter, PNCounter, ORSet, MVRegister and assert `load_entries()` exactly restores each state/version/context.

- [ ] **Step 2: Write transaction rollback test**

Monkeypatch the repository entry encoder to raise after the transaction begins but before commit. After failure, reopen DB and assert neither the candidate clock nor candidate entry was committed.

- [ ] **Step 3: Verify RED**
- [ ] **Step 4: Implement with explicit transaction**

```python
conn.execute("BEGIN IMMEDIATE")
try:
    # upsert causal_clock
    # upsert crdt_entries
except BaseException:
    conn.rollback()
    raise
else:
    conn.commit()
```

- [ ] **Step 5: Run**

```bash
python -m pytest -q tests/unit/persistence/test_sqlite_repository.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/distsys/persistence/sqlite_repository.py tests/unit/persistence/test_sqlite_repository.py
git commit -m "feat: atomically persist causal crdt mutations"
```

### Task 8: Durable observed-entry and authority updates

**Files:**
- Modify: `src/distsys/persistence/sqlite_repository.py`
- Test: `tests/unit/persistence/test_sqlite_repository.py`

**Interfaces:**
- `commit_observed_entry(entry, causal_state, deadline=None)`
- `mark_authority(key, authoritative)`

- [ ] **Step 1: Write observed-entry test**

Persist an incoming replicated entry plus advanced causal frontier; reopen; assert both are durable.

- [ ] **Step 2: Write authority test**

Mark key false, reload DB row, assert `last_authoritative == 0`; mark true and assert 1.

- [ ] **Step 3: Implement with transactions**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/persistence/test_sqlite_repository.py
git add src/distsys/persistence/sqlite_repository.py
git commit -m "feat: persist observed replica state and authority"
```

### Task 9: SQLite online backup

**Files:**
- Create: `src/distsys/persistence/backup.py`
- Modify: `src/distsys/persistence/sqlite_repository.py`
- Test: `tests/unit/persistence/test_backup.py`

**Interfaces:**
- `backup_sqlite(source_path, destination_path) -> Path`
- repository `backup(destination) -> Path`

- [ ] **Step 1: Write live-WAL backup test**

Open repository, commit a CRDT entry, leave DB active, call backup, then open backup with a fresh repository and assert the entry exists.

- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement using `sqlite3.Connection.backup()`**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/persistence/test_backup.py
git add src/distsys/persistence/backup.py src/distsys/persistence/sqlite_repository.py tests/unit/persistence/test_backup.py
git commit -m "feat: add safe sqlite online backup"
```

### Task 10: Persistence settings and filesystem hygiene

**Files:**
- Modify: `src/distsys/utils/config.py`
- Modify: `.env.example`
- Modify: `.gitignore`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/persistence/test_models.py`

**Interfaces:**
- Settings:
  - `persistence_enabled=True`
  - `persistence_db_path="./data/node.db"`
  - `persistence_queue_capacity=100`
  - `persistence_busy_timeout_seconds=5.0`
  - `persistence_sqlite_synchronous="NORMAL"`

- [ ] **Step 1: Add default-setting tests**
- [ ] **Step 2: Add invalid capacity/busy-timeout/synchronous-mode tests**
- [ ] **Step 3: Implement environment parsing and validation**

Allow synchronous values `OFF`, `NORMAL`, `FULL`, `EXTRA`; Phase-5 default remains `NORMAL`.

- [ ] **Step 4: Add ignored paths**

```gitignore
certs/generated/
data/*.db
data/*.db-wal
data/*.db-shm
.phase5-logs/
```

- [ ] **Step 5: Run complete 5A gate**

```bash
python -m pytest -q tests/unit/persistence tests/unit/test_config.py
python -m ruff check src/distsys/persistence tests/unit/persistence src/distsys/utils/config.py
python -m black --check src/distsys/persistence tests/unit/persistence src/distsys/utils/config.py
python -m mypy src/distsys/persistence
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/distsys/utils/config.py .env.example .gitignore tests/unit/test_config.py
git commit -m "feat: configure phase five persistence"
```
