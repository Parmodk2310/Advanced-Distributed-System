# Advanced Distributed System — Phase 5

A correctness-first distributed systems project built in incremental releases. The current `v0.5.0` target extends the Phase-4 causally consistent CRDT cluster with local durability, deterministic restart recovery, etcd-backed discovery/leases, and TLS 1.3 mutual authentication.

## Current architecture

```text
                         etcd
                  discovery + leases
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
   ┌─────────┐       ┌─────────┐       ┌─────────┐
   │ node-0  │◄─────►│ node-1  │◄─────►│ node-2  │
   │ :18000  │ mTLS  │ :18001  │ mTLS  │ :18002  │
   ├─────────┤       ├─────────┤       ├─────────┤
   │ SWIM    │       │ SWIM    │       │ SWIM    │
   │ CRDTs   │       │ CRDTs   │       │ CRDTs   │
   │ causal  │       │ causal  │       │ causal  │
   │ repair  │       │ repair  │       │ repair  │
   │ SQLite  │       │ SQLite  │       │ SQLite  │
   └─────────┘       └─────────┘       └─────────┘
```

Responsibility boundaries:

```text
SQLite/WAL        local durable CRDT + causal recovery state
etcd              discovery, lease registration, coordination metadata
SWIM-lite         live membership and failure detection
consistent hash   replica placement and routing
CRDT layer        merge/convergence semantics
TLS 1.3 + mTLS    encrypted authenticated node/client transport
```

## What Phase 5 adds

- SQLite WAL-backed local persistence with schema versioning.
- Stable node installation UUID and durable causal actor/counter/frontier.
- Atomic persistence of CRDT state, `state_version`, `causal_context`, and causal-clock advancement.
- Persist-before-memory behavior for local writes, replication, causal repair, and anti-entropy merges.
- Bounded `PersistenceExecutor` so disk saturation cannot create unbounded async work.
- Safe SQLite online backup.
- etcd member registration, discovery, TTL leases, renewal, and recovery.
- SWIM remains the live failure detector; etcd does not replace it.
- TLS 1.3 secure profile with mutual certificate verification.
- Logical certificate SAN binding to `node_id`, preventing one valid cluster certificate from impersonating another node.
- Recovery readiness gate: application CRDT reads/writes are rejected with `RECOVERY_IN_PROGRESS` until restore/reconciliation completes.
- Restart reconciliation: stale disk state merges with newer live replica state using the existing CRDT/VersionVector rules.

## Durability semantics

A successful Phase-5 mutation means the local node committed the mutation durably before ACK:

```text
causal validation
      ↓
persistence admission
      ↓
replication reservation
      ↓
staged Dot + CRDT state
      ↓
SQLite transaction
  ├─ CRDT state
  ├─ state_version
  ├─ causal_context
  └─ causal clock
      ↓
COMMIT
      ↓
install in memory
      ↓
async replication
      ↓
ACK
```

This is a **locally durable acknowledgement**, not a quorum-durable acknowledgement. The replication outbox remains volatile. If a node ACKs after local commit and crashes before fan-out, its local database restores the write and anti-entropy repairs other replicas after restart.

Phase 5 does **not** claim exactly-once execution, linearizability, consensus, distributed transactions, or quorum writes.

## Causal identity across restart

SWIM membership incarnation and causal actor incarnation are deliberately separate:

```text
before restart
SWIM incarnation     900
causal actor          node-2@500
local causal counter  41

normal restart
SWIM incarnation     901      # new process epoch
causal actor          node-2@500
local causal counter  41      # restored
next Dot              node-2@500:42
```

This prevents causal counter rollback or Dot reuse after an ordinary crash/restart.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Regenerate Protobuf after schema changes:

```bash
make proto
```

## Quality gate

```bash
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
```

The normal pytest suite skips the tests that require a live etcd service unless explicitly enabled. Run the required real-etcd gate with:

```bash
make phase5-etcd-integration
```

That target starts the pinned local etcd container, forces the live-etcd tests to run, and tears the container down afterward.

## Development certificates

Generate the local development PKI:

```bash
make phase5-certs
```

Generated material lives under `certs/generated/` and is ignored by Git. The generated CA/private keys are **development only**.

## Secure three-node validation

The complete managed system validation is:

```bash
make phase5-secure-smoke
```

It owns its temporary certificates, databases, node processes, and etcd container. The expected final marker is:

```text
PHASE5_SMOKE=PASS
```

The smoke covers:

- three-node mTLS startup,
- durable GCounter/PNCounter/ORSet/MVRegister operations,
- SQLite schema/identity verification,
- unknown-CA rejection,
- wrong-node certificate identity rejection,
- plaintext-to-TLS rejection,
- node restart with the same durable causal actor and a new SWIM epoch,
- stale-state reconciliation,
- data-plane operation during an etcd outage,
- lease/member registration recovery after etcd returns.

## Manual Phase-5 cluster

Terminal 1:

```bash
make phase5-certs
make phase5-cluster
```

Terminal 2:

```bash
make phase5-smoke
```

Optional managed checks while the launcher is running:

```bash
make phase5-restart-smoke
make phase5-etcd-smoke
```

## Main source layout

```text
src/distsys/
├── causal/          dotted/version-vector causal metadata
├── crdt/            GCounter, PNCounter, ORSet, MVRegister
├── storage/         in-memory state contracts
├── replication/     fan-out, causal repair, anti-entropy
├── persistence/     SQLite repository, codec, migrations, executor, backup
├── coordination/    etcd adapter, leases, discovery
├── security/        TLS contexts and certificate identity verification
├── recovery/        restore and reconciliation orchestration
├── health/          readiness/coordination/cluster health state
├── crdt_service.py
├── crdt_client.py
└── node.py
```

## Protocol compatibility

Phase-5 error codes append to the existing values without renumbering earlier releases:

```text
12 PERSISTENCE_UNAVAILABLE
13 PERSISTENCE_BACKPRESSURE
14 RECOVERY_IN_PROGRESS
15 COORDINATION_UNAVAILABLE
16 TLS_AUTHENTICATION_FAILED
```

Existing `MessageType` values 1–18 and `ErrorCode` values 0–11 remain unchanged.

## Project progression

See [`docs/PHASES.md`](docs/PHASES.md) for the complete Phase 1–7 roadmap and [`docs/PHASE5_VERIFICATION.md`](docs/PHASE5_VERIFICATION.md) for the Phase-5 release gate.

## Explicit non-goals for Phase 5

- Raft/consensus
- linearizable writes
- cross-key ACID transactions
- exactly-once execution
- durable replication outbox
- persisted idempotency-key deduplication
- distributed ORSet tombstone GC
- live certificate rotation
- user authentication/RBAC
- Kubernetes/Terraform
- full chaos campaign

Those belong to later phases rather than being hidden behind misleading claims in `v0.5.0`.
