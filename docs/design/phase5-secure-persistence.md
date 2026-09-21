# Phase 5 Secure Persistence & Recovery — Design Specification

> **Document status:** Historical design record. Phase 5 is implemented and verified. This file preserves the original pre-release design; see the [current architecture](../architecture/phase5-secure-persistence.md) and [verification record](../verification/phase5.md).

**Date:** 2026-09-13  
**Baseline:** `v0.4.0`  
**Feature branch:** `phase/5-secure-persistence`  
**Target release:** `v0.5.0`  
**Milestone:** Secure Persistence & Recovery

---

## 1. Purpose

Phase 5 transforms the Phase-4 in-memory causal CRDT cluster into a crash-recoverable, securely networked distributed system.

The design adds:

- durable CRDT state,
- durable causal metadata,
- stable node installation identity,
- deterministic crash/restart recovery,
- etcd-backed discovery and lease coordination,
- TLS 1.3 peer transport,
- mutual TLS authentication,
- certificate identity binding to `node_id`,
- readiness/recovery state,
- bounded persistence backpressure,
- restart reconciliation through the existing Phase-4 CRDT merge and anti-entropy mechanisms.

Phase 5 preserves the core Phase-4 model:

- primary-less CRDT writes,
- no write quorum,
- no consensus,
- state-based CRDT replication,
- session causal consistency,
- targeted causal read/write repair,
- digest-driven anti-entropy,
- SWIM-lite live failure detection,
- consistent-hash replica placement.

Phase 5 changes the durability semantics of a successful mutation: a successful client mutation must be committed to the local durable repository before acknowledgement.

---

## 2. Architectural Principles

### 2.1 Responsibility boundaries

Each subsystem has one primary responsibility:

| Subsystem | Responsibility |
|---|---|
| `CrdtService` | causal read/write semantics |
| `CrdtStore` | in-memory working CRDT state |
| `ReplicationService` | replica fan-out, repair, anti-entropy |
| `StateRepository` | durable state and recovery metadata |
| `PersistenceExecutor` | bounded async-to-blocking persistence bridge |
| `CoordinationService` | etcd registration, lease, discovery |
| SWIM-lite | live cluster membership and failure detection |
| `TLSContextFactory` / security package | transport security and peer identity |
| `RecoveryCoordinator` | ordered startup restore/reconciliation |
| health state | liveness/readiness/coordination/cluster status |

CRDT domain classes remain pure and do not import or call SQLite, etcd, TLS, or networking code.

### 2.2 Durable state versus coordination state

Application state is persisted locally in SQLite.

etcd stores only coordination/discovery metadata.

SWIM remains the source for live routing membership.

TLS secures transport but does not alter CRDT semantics.

```text
CRDT + causal state  -> SQLite/WAL
Discovery + leases   -> etcd
Live membership      -> SWIM-lite
Routing              -> Phase-3 consistent hash ring
Peer security        -> TLS 1.3 + mTLS
Convergence          -> Phase-4 merge + anti-entropy
```

---

## 3. High-Level Topology

```text
                    ┌─────────────────────────────┐
                    │            etcd             │
                    │ discovery · leases · config │
                    └──────────────┬──────────────┘
                                   │
                            coordination only
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
      ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
      │    node-0    │◄───►│    node-1    │◄───►│    node-2    │
      │              │mTLS │              │mTLS │              │
      │ SWIM         │     │ SWIM         │     │ SWIM         │
      │ CRDT store   │     │ CRDT store   │     │ CRDT store   │
      │ causal clock │     │ causal clock │     │ causal clock │
      │ replication  │     │ replication  │     │ replication  │
      │ anti-entropy │     │ anti-entropy │     │ anti-entropy │
      │ SQLite/WAL   │     │ SQLite/WAL   │     │ SQLite/WAL   │
      └──────────────┘     └──────────────┘     └──────────────┘
```

---

## 4. Source Layout

Phase 5 introduces focused packages instead of adding persistence and TLS logic directly to `node.py`.

```text
src/distsys/
├── causal/                         # Phase 4
├── crdt/                           # Phase 4
├── storage/                        # Phase 4 in-memory store
├── replication/                    # Phase 4
│
├── persistence/                    # NEW
│   ├── __init__.py
│   ├── models.py
│   ├── codec.py
│   ├── repository.py
│   ├── sqlite_repository.py
│   ├── migrations.py
│   ├── executor.py
│   └── backup.py
│
├── coordination/                   # NEW
│   ├── __init__.py
│   ├── models.py
│   ├── client.py
│   ├── etcd_client.py
│   ├── lease.py
│   ├── discovery.py
│   └── service.py
│
├── security/                       # NEW
│   ├── __init__.py
│   ├── tls_context.py
│   ├── certificate.py
│   └── identity.py
│
├── recovery/                       # NEW
│   ├── __init__.py
│   ├── restore.py
│   ├── reconciliation.py
│   └── coordinator.py
│
├── health/
│   ├── __init__.py
│   └── state.py
│
├── crdt_service.py                 # MODIFY
├── crdt_client.py                  # MODIFY
├── node.py                         # MODIFY
└── utils/config.py                 # MODIFY
```

Additional runtime assets:

```text
scripts/
├── generate_dev_certs.sh
├── run_phase5_cluster.sh
├── phase5_smoke.py
├── phase5_restart_smoke.py
└── phase5_etcd_smoke.py

docker/
└── etcd/
    └── docker-compose.yml
```

---

## 5. Persistence Abstraction

### 5.1 `StateRepository`

Persistence is hidden behind a repository protocol.

Conceptual interface:

```python
class StateRepository(Protocol):
    async def open(self) -> None: ...
    async def close(self) -> None: ...

    async def integrity_check(self) -> RepositoryHealth: ...

    async def load_identity(self) -> DurableNodeIdentity | None: ...
    async def initialize_identity(
        self,
        *,
        configured_node_id: str,
    ) -> DurableNodeIdentity: ...

    async def load_clock(self) -> DurableCausalState: ...
    async def load_entries(self) -> tuple[StoredCrdtEntry, ...]: ...

    async def commit_mutation(
        self,
        *,
        entry: StoredCrdtEntry,
        causal_state: DurableCausalState,
    ) -> None: ...

    async def merge_replica_state(
        self,
        *,
        entry: StoredCrdtEntry,
    ) -> StoredCrdtEntry: ...

    async def mark_authority(
        self,
        *,
        key: str,
        authoritative: bool,
    ) -> None: ...

    async def backup(self, destination: Path) -> Path: ...
```

The actual implementation must follow the existing repository typing conventions and may refine method return wrappers, but it must preserve these semantics.

### 5.2 Repository rules

- no application-layer SQL outside the persistence package,
- no pickle,
- deterministic durable encoding,
- atomic mutation transaction for CRDT state and causal metadata,
- explicit schema version,
- database corruption is startup-fatal,
- unsupported newer schema is startup-fatal,
- repository failures never cause silent empty-store initialization.

---

## 6. Durable Data Model

### 6.1 Database schema v1

Initial SQLite schema:

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at_ns INTEGER NOT NULL
);

CREATE TABLE node_identity (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    node_uuid TEXT NOT NULL UNIQUE,
    configured_node_id TEXT NOT NULL,
    causal_incarnation INTEGER NOT NULL,
    created_at_ns INTEGER NOT NULL,
    updated_at_ns INTEGER NOT NULL
);

CREATE TABLE causal_clock (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    local_counter INTEGER NOT NULL,
    frontier_json TEXT NOT NULL,
    updated_at_ns INTEGER NOT NULL
);

CREATE TABLE crdt_entries (
    key TEXT PRIMARY KEY,
    crdt_type TEXT NOT NULL,
    state_json TEXT NOT NULL,
    state_version_json TEXT NOT NULL,
    causal_context_json TEXT NOT NULL,
    last_authoritative INTEGER NOT NULL CHECK (last_authoritative IN (0, 1)),
    updated_at_ns INTEGER NOT NULL
);
```

### 6.2 Durable identity

Conceptual model:

```python
@dataclass(frozen=True, slots=True)
class DurableNodeIdentity:
    node_uuid: UUID
    configured_node_id: str
    causal_incarnation: int
```

The UUID identifies the installed node instance independently from the configured `node_id`.

### 6.3 Durable causal state

Conceptual model:

```python
@dataclass(frozen=True, slots=True)
class DurableCausalState:
    actor: CausalActor
    local_counter: int
    frontier: VersionVector
```

The local causal actor incarnation is persisted and survives normal process restart.

---

## 7. Causal Identity Semantics

Phase 5 explicitly separates membership process incarnation from durable causal incarnation.

### 7.1 Membership incarnation

Used by SWIM.

Properties:

- changes on process restart,
- rejects stale membership updates,
- represents a volatile process epoch.

### 7.2 Causal incarnation

Used by `CausalActor`.

Properties:

- persisted in SQLite,
- stable across ordinary crashes/restarts,
- changes only when a new durable installation identity is created,
- local causal counter is restored with it.

Example:

```text
before crash:
SWIM incarnation   = 900
causal actor       = node-0@500
local counter      = 418

after restart:
SWIM incarnation   = 901
causal actor       = node-0@500
local counter      = 418

next Dot           = (node-0@500, 419)
```

A normal restart must not create `(node-0@500, 1)`.

A normal restart also does not need to replace the causal actor with the new SWIM incarnation.

### 7.3 Fresh identity initialization

If the persistent database is intentionally removed or the node is initialized as a new installation:

- generate a new `node_uuid`,
- generate a new causal incarnation,
- initialize the local counter to zero,
- initialize an empty frontier.

This prevents Dot reuse between old and new durable installations.

---

## 8. Durable Encoding

All persisted CRDT state and causal metadata use deterministic structured encodings.

Canonical JSON requirements:

```python
json.dumps(
    value,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
)
```

Encoding must preserve:

- `CausalActor(node_id, causal_incarnation)`,
- Dot actor and counter,
- VersionVector entries,
- GCounter actor components,
- PNCounter positive and negative components,
- ORSet add-dot sets and removed-dot tombstones,
- MVRegister dot/value mappings and superseded dots,
- `state_version`,
- `causal_context`.

No Python `repr()` output is used as a durable contract.

---

## 9. SQLite Runtime Configuration

Default connection initialization:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = <configured milliseconds>;
```

### 9.1 WAL intent

WAL is selected for:

- crash recovery,
- predictable concurrent reads,
- practical single-node write performance,
- safe online backup support.

### 9.2 Synchronous mode

Default is:

```text
NORMAL
```

The setting is configurable, but Phase 5 examples and tests use the approved default unless a test intentionally exercises a stricter mode.

---

## 10. Async Persistence Boundary

`sqlite3` operations are blocking.

They must not execute directly on the asyncio event loop.

Architecture:

```text
async CRDT service
       │
       ▼
PersistenceExecutor
       │
       ├── bounded admission
       │
       ▼
asyncio.to_thread(...)
       │
       ▼
SQLiteStateRepository
```

### 10.1 Persistence queue

Default:

```text
PERSISTENCE_QUEUE_CAPACITY=100
```

If capacity is exhausted before a mutation begins, return:

```text
PERSISTENCE_BACKPRESSURE
```

No visible CRDT mutation may occur first.

### 10.2 Deadline behavior

Persistence admission and durable commit consume the existing request monotonic deadline.

A fresh persistence timeout is not created.

---

## 11. Durable Mutation Path

Phase-5 client mutation order is:

```text
1. validate request
2. route to authoritative replica
3. validate client causal token
4. targeted causal repair if local context is stale
5. reserve bounded persistence capacity
6. reserve replication outbox responsibility
7. acquire per-key mutation serialization
8. revalidate required causal condition
9. derive candidate Dot and candidate CRDT state
10. execute one SQLite transaction:
    - update local causal counter/frontier
    - persist CRDT state
    - persist state_version
    - persist causal_context
11. COMMIT
12. install committed entry and causal state in memory
13. publish async replication snapshot
14. return success + updated CausalToken
```

### 11.1 Atomicity requirement

These values must commit atomically:

```text
CRDT state
state_version
causal_context
local causal counter
local causal frontier
```

A crash cannot produce a new CRDT value with the old local causal clock.

A crash cannot produce a new clock without the CRDT mutation associated with the allocated Dot.

### 11.2 Successful acknowledgement semantics

A successful mutation means:

- local durable commit succeeded,
- local in-memory state reflects the committed value,
- replication responsibility was admitted before mutation.

It does not mean:

- a second replica has persisted the write,
- a quorum accepted the write,
- exactly-once execution occurred.

---

## 12. Crash-After-Commit Semantics

If SQLite commit succeeds but the process dies before the client receives success:

```text
COMMIT
  ↓
process crash
  ↓
response not delivered
```

the mutation exists after restart.

The client may retry.

A non-idempotent operation may therefore be applied twice.

Phase 5 explicitly does not claim exactly-once semantics.

Idempotency-key persistence is deferred.

---

## 13. Incoming Replica Durability

Any incoming state that becomes visible as local state must become durable first.

This applies to:

- normal replication,
- anti-entropy repair,
- causal read repair,
- causal write repair,
- recovery reconciliation,
- replica reassignment state transfer.

Correct order:

```text
receive remote state
      ↓
validate
      ↓
CRDT merge
      ↓
durable transaction
      ↓
COMMIT
      ↓
install merged state in memory
      ↓
respond
```

Remote repair cannot acknowledge merged state before durability succeeds.

---

## 14. Replication Outbox Semantics

The Phase-4 replication outbox remains in memory.

It is not persisted in Phase 5.

Therefore:

```text
local durable COMMIT
        ↓
client ACK
        ↓
process crash before replication
```

may temporarily leave only one durable copy.

After restart, restored durable state plus Phase-4 anti-entropy repairs other replicas.

The release documentation must use the term:

```text
locally durable acknowledgement
```

and must not imply replicated-durable acknowledgement.

---

## 15. Recovery Lifecycle

A node has explicit startup states:

```text
STARTING
OPENING_REPOSITORY
RESTORING
BINDING
COORDINATING
JOINING_CLUSTER
RECONCILING
READY
STARTUP_FAILED
```

Coordination can independently become degraded after readiness.

### 15.1 Readiness

Normal CRDT operations are not accepted until state is `READY`.

Before readiness, application CRDT requests receive:

```text
RECOVERY_IN_PROGRESS
```

Control-plane communication necessary for bootstrap/reconciliation may run before application readiness.

---

## 16. Exact Startup Order

Startup order:

```text
1. parse and validate configuration
2. build TLS contexts
3. open SQLite repository
4. read schema version
5. run supported schema migrations
6. run repository integrity validation
7. load or initialize durable node identity
8. restore causal actor, counter, and frontier
9. restore CRDT entries into CrdtStore
10. bind network listener
11. connect to etcd
12. obtain/register lease
13. discover bootstrap peers
14. start/join SWIM cluster
15. recalculate current replica ownership
16. mark restored non-owned keys non-authoritative
17. run recovery reconciliation against live replicas
18. start normal anti-entropy loop
19. transition to READY
```

If configured clustered CRDT startup requires etcd discovery and no valid bootstrap knowledge exists, inability to contact etcd causes startup failure.

---

## 17. Restore and Reconciliation

Disk state is locally durable history, not proof of global freshness.

Example:

```text
node-2 durable version 15
node-2 stops

node-0/node-1 advance to 19

node-2 restarts
  ↓
load durable 15
  ↓
join cluster
  ↓
compare digests
  ↓
merge newer/concurrent state
  ↓
persist merged result
  ↓
READY
```

Phase-5 recovery reuses:

- VersionVector comparison,
- CRDT merge,
- digest comparison,
- anti-entropy transport.

It does not introduce a second recovery-specific conflict algorithm.

---

## 18. Replica Ownership After Recovery

Restored keys are evaluated against the current consistent-hash replica set.

If the node remains an authoritative replica:

- key remains active.

If the node is no longer an authoritative replica:

- persisted state is retained,
- `last_authoritative` becomes false,
- normal read/write routing must not treat that copy as authoritative.

Phase 5 does not implement distributed safe deletion of old replicas.

---

## 19. Tombstones and Garbage Collection

ORSet removed-dot tombstones remain durable.

Phase 5 does not add distributed causal tombstone garbage collection.

Phase 5 does not automatically delete obsolete replica state.

Both require additional distributed safety rules and remain out of scope.

---

## 20. Schema Versioning and Migrations

The repository has explicit schema versioning from the first Phase-5 release.

Startup behavior:

```text
db version == current
    -> continue

db version < current
    -> execute ordered supported migrations

db version > current
    -> fail startup
```

Migrations are centrally defined in `persistence/migrations.py`.

Schema mutation is not scattered through repository read/write methods.

Where SQLite permits, each migration runs transactionally.

A migration failure leaves startup failed and does not silently recreate the database.

---

## 21. Database Corruption and Identity Mismatch

The following are startup-fatal:

- database cannot open,
- integrity check fails,
- unsupported newer schema,
- migration fails,
- durable node identity record is malformed,
- configured `node_id` conflicts with the durable installation identity policy,
- causal state is malformed,
- required TLS material is missing or invalid.

The implementation must never respond to these conditions by deleting the existing database.

---

## 22. Backup

Phase 5 provides a safe local backup operation using SQLite backup semantics.

Correct behavior:

```text
live SQLite DB
   ↓
SQLite backup API
   ↓
consistent backup DB
```

A raw filesystem copy of the main database file while WAL writes are active is not the supported backup path.

Automated remote backup orchestration remains out of scope.

---

## 23. etcd Responsibility

etcd is used for:

- durable node discovery metadata,
- ephemeral member registration through leases,
- advertised host/port,
- node installation UUID metadata,
- current SWIM process incarnation metadata,
- protocol/release metadata,
- cluster-level configuration metadata where explicitly needed.

etcd is not used for:

- CRDT application payloads,
- causal_context,
- state_version,
- CRDT tombstones,
- replication outbox,
- SQLite backup contents.

---

## 24. etcd Namespace

Versioned namespace:

```text
/distsys/v1/
├── members/
│   └── {node_id}
├── nodes/
│   └── {node_id}/metadata
└── config/
    └── {key}
```

Example member record:

```json
{
  "node_id": "node-0",
  "node_uuid": "stable-installation-uuid",
  "host": "127.0.0.1",
  "port": 18000,
  "membership_incarnation": 12345,
  "protocol_version": 5,
  "release": "0.5.0",
  "tls_required": true
}
```

---

## 25. Coordination Abstraction

Conceptual protocol:

```python
class CoordinationClient(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...

    async def grant_lease(self, ttl_seconds: int) -> LeaseHandle: ...
    async def keep_alive(self, lease: LeaseHandle) -> None: ...

    async def register_member(
        self,
        *,
        member: CoordinationMember,
        lease: LeaseHandle,
    ) -> None: ...

    async def discover_members(self) -> tuple[CoordinationMember, ...]: ...
```

The etcd implementation is behind this interface so unit tests do not require an etcd daemon.

---

## 26. Lease Semantics

Defaults:

```text
ETCD_LEASE_TTL_SECONDS=15
ETCD_RENEW_INTERVAL_SECONDS=5
```

Validation:

```text
renew interval < lease TTL
```

A node registration is attached to its lease.

Lease expiration removes the ephemeral `/members/{node_id}` key.

The durable `/nodes/{node_id}/metadata` record can remain independent from the ephemeral live registration if the implementation uses that separation.

---

## 27. etcd and SWIM Interaction

etcd and SWIM have different jobs.

```text
etcd
  -> bootstrap/discovery
  -> lease-based stale discovery cleanup

SWIM
  -> ALIVE/SUSPECT/DEAD
  -> fast live failure detection
  -> routing membership
```

etcd does not replace the Phase-3 SWIM state machine.

SWIM does not become persistent discovery storage.

---

## 28. etcd Outage Policy

### 28.1 Outage after READY

If etcd becomes unavailable after the node is fully ready:

- current SWIM membership remains valid,
- safe CRDT reads continue,
- safe CRDT writes continue,
- replication continues,
- anti-entropy continues,
- coordination health becomes degraded,
- etcd reconnection/lease acquisition retries continue.

The node does not immediately exit.

### 28.2 Cold start with no discovery state

If clustered CRDT mode is enabled, no valid bootstrap peers are available, and etcd is unavailable:

- startup fails closed,
- the node does not silently form a new independent cluster.

Single-node/non-cluster operation remains separate from this rule.

---

## 29. Coordination Recovery

When etcd becomes reachable again:

```text
reconnect
   ↓
grant/acquire lease
   ↓
restore ephemeral member registration
   ↓
coordination health = healthy
```

This process must not reset CRDT state or causal identity.

---

## 30. TLS Scope

Phase 5 secures node-to-node and cluster protocol traffic first.

Transport stack:

```text
TCP
 ↓
TLS 1.3
 ↓
mutual certificate validation
 ↓
node identity validation
 ↓
existing framed protocol
 ↓
Protobuf
```

The existing Phase-1 protocol framing remains the application framing layer after TLS establishment.

---

## 31. TLS Version

Secure Phase-5 mode requires:

```text
minimum TLS version = TLS 1.3
```

The secure profile does not fall back to TLS 1.2 or older.

---

## 32. Mutual TLS

When:

```text
TLS_ENABLED=true
MTLS_REQUIRED=true
```

both sides must present certificates trusted by the configured cluster CA.

A connection is accepted only when:

- the TLS handshake succeeds,
- certificate chain validation succeeds,
- certificate time validity succeeds,
- the peer identity matches the expected cluster member.

---

## 33. Certificate Identity Binding

A valid certificate signed by the cluster CA is not sufficient if it identifies the wrong node.

If routing expects `node-1` but the authenticated certificate identifies `node-2`, the peer connection is rejected.

Development certificates use SAN entries containing node identity, for example:

```text
DNS:node-1
IP:127.0.0.1
```

The implementation must distinguish:

- transport hostname/IP verification,
- logical `node_id` verification.

The logical peer identity check is mandatory for cluster peer connections in secure mode.

---

## 34. TLS Files and Secret Handling

Runtime inputs:

```text
ca.crt
node.crt
node.key
```

Files are configured through settings/environment.

Private keys:

- are never embedded in source,
- are never embedded in Protobuf,
- are never logged,
- must be readable by the process,
- should have restrictive filesystem permissions.

Development CA private keys are generation assets only and are not distributed as runtime node credentials.

---

## 35. Development Certificates

Provide:

```text
scripts/generate_dev_certs.sh
```

It creates a local development CA and certificates for:

- node-0,
- node-1,
- node-2.

The script and documentation must explicitly label the generated PKI:

```text
DEVELOPMENT ONLY
```

Generated private keys are ignored by Git.

---

## 36. TLS Compatibility Modes

Default compatibility configuration:

```text
TLS_ENABLED=false
MTLS_REQUIRED=false
```

Secure Phase-5 validation profile:

```text
TLS_ENABLED=true
MTLS_REQUIRED=true
TLS_MIN_VERSION=TLSv1.3
```

If TLS is enabled, plaintext connections to that listener are rejected.

There is no automatic plaintext/TLS protocol sniffing on the same port.

---

## 37. Certificate Rotation

Phase 5 supports restart-based certificate replacement:

```text
replace certificate/key files
   ↓
restart node
   ↓
new SSL context loaded
```

Hot reload and zero-downtime certificate rotation are deferred.

---

## 38. TLS Error Semantics

Phase 5 appends:

```text
TLS_AUTHENTICATION_FAILED
```

as a structured internal/application error classification.

Some TLS failures occur before the framed/Protobuf layer exists. For those failures, the connection may close without a Protobuf error response.

The failure must still be represented in structured logs/health diagnostics where practical.

---

## 39. Health Model

Phase 5 tracks four health dimensions.

### 39.1 Liveness

Process and event loop are running.

### 39.2 Readiness

Repository opened, durable state restored, cluster joined as required, recovery reconciliation completed, application CRDT service ready.

### 39.3 Coordination health

etcd connection and current lease/registration condition.

### 39.4 Cluster health

SWIM membership and healthy replica visibility.

Example valid state:

```text
liveness      = healthy
readiness     = ready
coordination  = degraded
cluster       = healthy
```

during a temporary post-start etcd outage.

---

## 40. New Error Codes

Phase 4 ends at:

```text
KEY_NOT_FOUND = 11
```

Phase 5 appends:

```text
12 PERSISTENCE_UNAVAILABLE
13 PERSISTENCE_BACKPRESSURE
14 RECOVERY_IN_PROGRESS
15 COORDINATION_UNAVAILABLE
16 TLS_AUTHENTICATION_FAILED
```

All existing numeric values `0..11` remain unchanged.

---

## 41. Request Deadline Semantics

The existing monotonic request deadline covers:

- routing,
- causal repair,
- persistence queue admission,
- SQLite durable commit,
- forwarding.

No Phase-5 subsystem resets the request timeout.

Background anti-entropy and etcd lease renewal use their own bounded background-operation timeouts because they are not part of an individual client request.

---

## 42. Persistence Backpressure

The durability layer is bounded.

If persistence admission cannot be obtained within the request's remaining deadline:

```text
PERSISTENCE_BACKPRESSURE
```

is returned before any visible memory mutation.

The implementation must not mutate in memory and then discover that durable capacity is unavailable.

---

## 43. Configuration

New conceptual settings:

```text
PERSISTENCE_ENABLED=true
PERSISTENCE_DB_PATH=./data/node.db
PERSISTENCE_QUEUE_CAPACITY=100
PERSISTENCE_BUSY_TIMEOUT_SECONDS=5
PERSISTENCE_SQLITE_SYNCHRONOUS=NORMAL

ETCD_ENABLED=true
ETCD_ENDPOINTS=http://127.0.0.1:2379
ETCD_NAMESPACE=/distsys/v1
ETCD_LEASE_TTL_SECONDS=15
ETCD_RENEW_INTERVAL_SECONDS=5

TLS_ENABLED=false
MTLS_REQUIRED=false
TLS_CA_FILE=
TLS_CERT_FILE=
TLS_KEY_FILE=
TLS_MIN_VERSION=TLSv1.3
```

### 43.1 Validation rules

- queue capacity >= 1,
- busy timeout > 0,
- lease TTL > 0,
- renew interval > 0,
- renew interval < lease TTL,
- `MTLS_REQUIRED=true` requires `TLS_ENABLED=true`,
- secure TLS mode requires CA, certificate, and private-key paths,
- persistence path parent must be creatable/writable,
- clustered cold-start etcd profile requires usable etcd endpoints.

---

## 44. Structured Observability

Phase 5 adds structured events.

Persistence:

```text
persistence_opened
persistence_commit_started
persistence_commit_succeeded
persistence_commit_failed
persistence_backpressure
```

Migration:

```text
schema_migration_started
schema_migration_completed
schema_migration_failed
```

Recovery:

```text
recovery_started
recovery_identity_restored
recovery_clock_restored
recovery_entries_restored
recovery_reconciliation_started
recovery_completed
```

Coordination:

```text
etcd_connected
etcd_lease_granted
etcd_lease_renewed
etcd_lease_lost
etcd_connection_lost
etcd_connection_restored
```

Security:

```text
tls_listener_started
tls_peer_authenticated
tls_peer_identity_mismatch
tls_handshake_rejected
```

CRDT durability:

```text
crdt_durable_mutation_committed
crdt_durable_replica_merge
```

Secret/key contents must never appear in logs.

Full Prometheus/Grafana expansion is deferred.

---

## 45. Backup and Filesystem Hygiene

Recommended ignored runtime artifacts:

```text
*.key
certs/generated/
data/*.db
data/*.db-wal
data/*.db-shm
```

Local runtime data and generated private keys are not committed.

---

## 46. Testing Architecture

Phase 5 retains all Phase-1 through Phase-4 tests and adds subsystem and integration coverage.

### 46.1 Persistence unit tests

Required behaviors:

- initialize new schema v1,
- reopen existing database,
- WAL configuration,
- node identity creation,
- node identity restore,
- identity mismatch rejection,
- causal actor restore,
- causal counter restore,
- causal frontier restore,
- GCounter round-trip,
- PNCounter round-trip,
- ORSet round-trip including removed dots,
- MVRegister round-trip including concurrent values,
- `state_version` round-trip,
- `causal_context` round-trip,
- atomic mutation commit,
- transaction rollback on failure,
- persistence admission backpressure,
- unsupported newer schema rejection,
- supported migration execution,
- migration failure,
- corruption/integrity failure,
- SQLite backup.

### 46.2 Recovery tests

Required behaviors:

```text
persisted CRDT survives restart
causal counter never regresses
same durable node never reuses a Dot
SWIM membership incarnation changes on process restart
durable causal actor remains stable on normal restart
restored stale state merges with newer live replica state
stale disk state cannot overwrite newer remote state
non-owned restored keys become non-authoritative
```

### 46.3 etcd unit/integration tests

Unit tests use a coordination fake.

Integration tests use a real local etcd process/container when available.

Required cases:

- registration,
- lease acquisition,
- lease renewal,
- lease expiration,
- member key cleanup,
- discovery,
- temporary post-READY outage,
- coordination degraded state,
- reconnect,
- lease reacquisition,
- registration restoration,
- cold-start etcd failure.

### 46.4 TLS integration tests

Required matrix:

| Client | Server / expectation | Result |
|---|---|---|
| valid node certificate | valid secure peer | success |
| unknown CA | valid server | fail |
| valid CA but wrong logical node identity | expected different node | fail |
| no client certificate | mTLS required | fail |
| plaintext connection | TLS listener | fail |
| expired/not-yet-valid certificate where practical | valid peer | fail |
| valid secure peers | Phase-4 CRDT replication | success |

### 46.5 Phase-4 regression tests

Secure persistence must not change the semantics of:

- GCounter,
- PNCounter,
- ORSet,
- MVRegister,
- targeted causal read repair,
- targeted causal write repair,
- read-your-writes,
- monotonic reads,
- monotonic writes,
- writes-follow-reads,
- cross-key causal session propagation,
- replication backpressure,
- anti-entropy convergence,
- replica reassignment,
- any-node ingress.

---

## 47. Canonical Restart Integration Scenario

```text
start node-0,node-1,node-2
        ↓
write CRDT key K = A
        ↓
wait for durable state
        ↓
stop node-2
        ↓
node-0/node-1 advance K to B
        ↓
restart node-2
        ↓
open SQLite
        ↓
restore A
        ↓
restore durable causal actor/counter
        ↓
new SWIM process incarnation
        ↓
acquire etcd lease
        ↓
join cluster
        ↓
recovery reconciliation
        ↓
merge A with B
        ↓
persist merged B
        ↓
READY
        ↓
all authoritative replicas converge
```

The test must prove stale restored state cannot overwrite newer live state.

---

## 48. Secure Phase-5 Smoke

Canonical full-system smoke:

```text
generate development CA/certificates
        ↓
start etcd
        ↓
start 3 SQLite-backed TLS nodes
        ↓
verify mTLS cluster convergence
        ↓
write/read all Phase-4 CRDTs
        ↓
verify durable database files
        ↓
stop one node
        ↓
continue writes with reduced live membership
        ↓
restart node
        ↓
restore SQLite state
        ↓
verify new SWIM incarnation
        ↓
verify same durable causal actor
        ↓
reacquire etcd lease
        ↓
reconcile with peers
        ↓
verify final convergence
        ↓
attempt bad/identity-mismatched certificate
        ↓
verify rejection
        ↓
stop etcd temporarily
        ↓
verify existing safe data-plane operations continue
        ↓
restart etcd
        ↓
verify lease/registration recovery
        ↓
PHASE5_SMOKE=PASS
```

---

## 49. Laptop-Safe Development Profile

Default local development topology:

```text
node-0: 127.0.0.1:18000
node-1: 127.0.0.1:18001
node-2: 127.0.0.1:18002
etcd:   127.0.0.1:2379
```

Conservative settings:

```text
CPU_WORKERS=1 per node
existing Phase-4 queue bounds
SQLite local files
one local etcd process/container
no Prometheus/Grafana during normal Phase-5 development
no chaos framework during Phase 5
```

---

## 50. Failure Semantics

| Failure | Required behavior |
|---|---|
| Node process crash | restore durable state on restart |
| SQLite commit failure | no successful mutation ACK and no visible new state |
| Persistence queue full | `PERSISTENCE_BACKPRESSURE` before mutation |
| Corrupt database | fail startup |
| Unsupported newer schema | fail startup |
| Node identity mismatch | fail startup |
| etcd unavailable after READY | coordination degraded; safe data plane continues |
| etcd unavailable at unbootstrapped clustered cold start | fail closed |
| Lease expires | ephemeral member registration removed |
| Replica stale after restart | recovery/anti-entropy merge |
| Peer unknown CA | TLS handshake rejected |
| Peer valid CA but wrong `node_id` | identity rejected |
| Plaintext to TLS port | connection rejected |
| Crash after commit before ACK | mutation may exist; retry may repeat |
| Crash after ACK before fan-out | local durable state restored; anti-entropy repairs |

---

## 51. Security Boundaries

Phase 5 secures peer authenticity and confidentiality.

It does not provide end-user authorization.

Explicitly deferred:

- user accounts,
- bearer-token authentication,
- RBAC,
- per-key authorization,
- Vault/cloud secret manager,
- automatic CA lifecycle.

mTLS certificates establish node identity, not human/user identity.

---

## 52. Non-Goals

Phase 5 explicitly does not include:

- Raft or another consensus protocol,
- linearizable data semantics,
- write quorum,
- distributed SQL,
- cross-key ACID transactions,
- exactly-once request execution,
- durable replication outbox,
- persisted idempotency-key deduplication,
- safe distributed ORSet tombstone garbage collection,
- automatic deletion of obsolete replicas,
- hot TLS certificate rotation,
- user authentication/RBAC,
- secrets manager integration,
- Kubernetes,
- Terraform,
- Prometheus/Grafana expansion,
- full chaos/fault campaign.

These omissions are intentional scope boundaries.

---

## 53. Guarantees After Successful Completion

Phase 5 may claim:

- locally durable acknowledged CRDT mutations,
- durable causal counter/frontier,
- no local Dot reuse after ordinary crash/restart,
- stable durable node installation identity,
- deterministic local restart restoration,
- CRDT reconciliation after offline periods,
- stale disk state cannot overwrite newer CRDT state through assignment,
- etcd-backed discovery registration,
- lease-based cleanup of stale discovery entries,
- SWIM live failure detection,
- TLS 1.3 encrypted secure profile,
- mutual TLS peer authentication,
- logical node-ID certificate verification,
- safe degraded data-plane operation during temporary post-start etcd outage.

Phase 5 may not claim:

- quorum durability,
- linearizability,
- consensus,
- exactly-once semantics,
- distributed transactions,
- durability against physical loss of the only disk containing an acknowledged pre-replication mutation,
- durable replication scheduling,
- zero-downtime certificate rotation.

---

## 54. Protocol Compatibility

Existing `MessageType` numeric values from Phases 1-4 remain unchanged.

Existing `ErrorCode` numeric values `0..11` remain unchanged.

New Phase-5 error values are appended only.

Any additional Phase-5 protocol messages required for health/coordination are appended without renumbering older messages.

Protobuf source remains the canonical wire-schema source and generated files are regenerated using the project's existing compiler/tooling.

---

## 55. Documentation Requirements

`README.md` and Phase documentation must clearly explain:

- SQLite is authoritative only for local durable recovery state,
- etcd is coordination/discovery, not CRDT storage,
- SWIM remains live membership/failure detection,
- mTLS authenticates nodes,
- a successful mutation is locally durable but not quorum-durable,
- replication outbox remains volatile,
- exactly-once is not provided,
- restart reconciliation can advance restored stale state,
- secure and plaintext modes are explicitly configured rather than auto-detected.

---

## 56. Git and Release Workflow

Feature branch:

```text
phase/5-secure-persistence
```

Release:

```text
v0.5.0
```

The release tag is annotated.

No `v0.5.0` tag is created before:

1. implementation is merged to `main`,
2. full quality gate passes on merged `main`,
3. secure smoke passes on merged `main`,
4. restart/recovery smoke passes,
5. etcd outage/recovery smoke passes,
6. invalid-certificate rejection passes.

Final remote verification:

```text
origin/main commit == v0.5.0^{}
```

---

## 57. Exit Criteria

### Persistence

- SQLite/WAL repository implemented.
- Schema version v1 implemented.
- Migration runner implemented.
- Stable node UUID persisted.
- Durable causal incarnation persisted.
- Durable causal counter/frontier persisted.
- All four CRDT states persisted.
- `state_version` persisted.
- `causal_context` persisted.
- Atomic mutation transaction implemented.
- Bounded persistence admission implemented.
- Safe SQLite backup implemented.

### Recovery

- cold local restore implemented,
- application traffic blocked before readiness,
- causal counter never moves backward,
- normal restart does not reuse a Dot,
- new SWIM incarnation appears after process restart,
- durable causal actor remains stable,
- stale restored state reconciles with live state,
- stale disk state cannot overwrite newer live CRDT state,
- restored non-owned keys are non-authoritative.

### Coordination

- etcd connection implemented,
- member registration implemented,
- lease acquisition implemented,
- periodic keepalive implemented,
- lease expiry behavior verified,
- discovery bootstrap implemented,
- post-start etcd outage degrades coordination rather than killing the data plane,
- etcd recovery reacquires lease and registration.

### Security

- TLS 1.3 secure profile implemented,
- mTLS implemented,
- cluster CA verification implemented,
- node identity SAN verification implemented,
- unknown CA rejected,
- identity mismatch rejected,
- missing client certificate rejected when required,
- plaintext rejected on TLS listener,
- secure CRDT replication verified.

### Compatibility

- Phase-1 tests pass,
- Phase-2 tests pass,
- Phase-3 tests pass,
- Phase-4 tests pass,
- MessageType numeric compatibility preserved,
- ErrorCode numeric compatibility preserved.

### Quality

- complete pytest suite passes,
- Ruff passes,
- Black passes,
- mypy passes,
- compileall passes,
- Protobuf generated successfully.

### System verification

- secure three-node smoke passes,
- restart/recovery smoke passes,
- etcd outage/recovery smoke passes,
- invalid-certificate smoke passes,
- all managed child processes stop cleanly,
- ports are released after tests,
- documentation matches actual implementation.

### Release

- feature branch pushed,
- review/PR completed,
- merged into `main`,
- post-merge verification passes,
- annotated `v0.5.0` pushed,
- `v0.5.0^{}` equals the Phase-5 release commit on `origin/main`.

Only after every applicable exit criterion passes is Phase 5 considered closed.

---

## 58. Implementation Decomposition

The architecture is intentionally decomposed into independent implementation workstreams:

```text
5A — Durable Persistence Foundation
    repository abstraction
    canonical durable codec
    SQLite/WAL schema
    migrations
    identity + causal state persistence
    backup

5B — Durable CRDT Integration
    persistence executor
    durable mutation path
    durable remote merge
    persistence backpressure
    restart restoration

5C — etcd Coordination
    client abstraction
    registration
    leases
    discovery
    degraded/recovery behavior

5D — TLS/mTLS Security
    SSL context construction
    dev certificates
    peer certificate validation
    logical node identity verification
    secure peer/client transport

5E — Recovery Orchestration
    startup state machine
    ownership recalculation
    recovery reconciliation
    readiness/health

5F — Full Verification & Release
    integration tests
    restart tests
    etcd outage tests
    TLS negative tests
    secure smoke
    documentation
    release gate
```

Each workstream should become a separate implementation plan section and should produce independently testable software before the next dependency layer is added.

---

## 59. Final Architecture Summary

Phase 5 preserves the distributed semantics built in Phases 1-4 while adding local durability, durable causal identity, secure transport, and durable discovery coordination.

The final responsibility model is:

```text
Client request
     │
     ▼
CrdtService
     │
     ├── causal semantics
     ├── persistence admission
     ├── durable commit
     └── replication scheduling
     │
     ▼
StateRepository / SQLite
     │
     └── local durable recovery state

ReplicationService
     │
     └── Phase-4 replication + repair + anti-entropy

CoordinationService / etcd
     │
     └── discovery + lease coordination

SWIM-lite
     │
     └── live membership + failure detection

TLS 1.3 + mTLS
     │
     └── secure authenticated peer transport

RecoveryCoordinator
     │
     └── restore + reconcile + readiness
```

This architecture targets `v0.5.0` as a secure, crash-recoverable causal CRDT cluster while intentionally avoiding consensus, quorum writes, exactly-once semantics, and distributed transactions.
