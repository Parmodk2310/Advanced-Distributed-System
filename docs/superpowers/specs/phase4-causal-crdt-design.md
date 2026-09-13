# Phase 4 — Causal Consistency & CRDT Replication Design

**Status:** Approved consolidated architecture, pending written-spec review  
**Target release:** `v0.4.0`  
**Base release:** `v0.3.0`  
**Feature branch:** `phase/4-causal-crdt`  
**Date:** 2026-09-13

## 1. Goal

Phase 4 extends the Phase-3 decentralized cluster with a causally consistent, primary-less, replicated CRDT data layer.

The system must support:

- session-wide causal consistency,
- causally unique mutation identity,
- GCounter, PNCounter, ORSet, and MVRegister,
- consistent-hash-based replica placement,
- local-first writes,
- asynchronous state-based replication,
- bounded/coalescing replication work,
- targeted causal read and write repair,
- digest-driven anti-entropy,
- temporary partition recovery,
- node restart/rejoin recovery,
- backward compatibility with all Phase-1/2/3 behavior.

Phase 4 intentionally does not add durable storage, write/read quorums, consensus, transactions, whole-key deletion, Merkle trees, or exactly-once delivery.

## 2. Architecture Summary

```text
Phase 3
SWIM membership
      |
      v
ALIVE members
      |
      v
ConsistentHashRing
      |
      v
replica candidates(key)
      |
      v
Phase 4 replica set
      |
      +-------------------------------+
      |                               |
      v                               v
Causal metadata                  CRDT state
VersionVector                    GCounter
Dot                              PNCounter
CausalToken                      ORSet
CausalClock                      MVRegister
      |                               |
      +---------------+---------------+
                      |
                      v
                 CrdtStore
                      |
          +-----------+-----------+
          |                       |
          v                       v
 local-first write         causal read/repair
          |                       |
          v                       v
 coalescing outbox      targeted replica fetch
          |                       |
          v                       v
 async replication          local merge
          |                       |
          +-----------+-----------+
                      |
                      v
             digest anti-entropy
                      |
                      v
                 convergence
```

## 3. Compatibility Constraints

Phase 4 must preserve:

- existing framing version,
- existing `MessageType` numeric values 1 through 11,
- existing `ErrorCode` numeric values 0 through 8,
- Phase-3 task routing behavior,
- Phase-3 cluster control behavior,
- existing `DistributedClient`,
- Phase-1/2/3 tests,
- cluster-disabled single-node operation.

`CRDT_ENABLED` defaults to `false`.

When `CRDT_ENABLED=false`, Phase-4 CRDT messages must not mutate CRDT state.

## 4. Replica Placement

Replica placement reuses the existing Phase-3 consistent-hash candidate order.

```text
replicas(key) =
    first CRDT_REPLICATION_FACTOR
    unique ALIVE members from
    ConsistentHashRing.candidates(key)
```

Default:

```text
CRDT_REPLICATION_FACTOR=3
```

If fewer ALIVE nodes are available than the configured replication factor, the effective replica set shrinks to the available ALIVE members.

No write quorum is introduced in Phase 4.

## 5. Causal Actor Identity

A causal mutation identity must not be reused after process restart.

Each process therefore derives a causal actor from the Phase-3 membership incarnation:

```text
CausalActor
├── node_id
└── incarnation
```

A restarted physical node has a newer Phase-3 incarnation and therefore becomes a different causal actor even when `node_id` is unchanged.

This allows the local mutation counter to restart from zero without colliding with pre-restart dots.

## 6. Dot

A causal mutation receives:

```text
Dot
├── actor
└── counter
```

For one causal actor, counters strictly increase.

No physical wall-clock timestamp participates in causal ordering.

## 7. VersionVector

`VersionVector` maps causal actors to the largest observed counter.

Required operations:

```python
merge(other)
compare(other)
dominates(other)
concurrent_with(other)
missing_from(other)
with_dot(dot)
```

Comparison semantics:

```text
A < B       A happened-before B
A > B       A happened-after B
A == B      identical causal frontier
A || B      concurrent
```

Merge is pointwise maximum.

## 8. CausalToken

Clients carry one session-wide causal token.

```text
CausalToken = serialized VersionVector
```

Every successful read or write returns a new token.

The client may pass that token into the next operation, including an operation on a different key.

This supports read-your-writes, monotonic reads, monotonic writes, writes-follow-reads, and cross-key causal dependency propagation.

## 9. CausalClock

Each running node has a `CausalClock` with local `CausalActor`, local counter, and observed causal frontier.

Before allocating a local mutation dot:

1. merge the incoming client token,
2. merge relevant local causal knowledge,
3. increment the local actor counter,
4. emit the new Dot,
5. include the Dot in the resulting causal frontier.

## 10. Stored Entry Model

Each CRDT key is represented as:

```text
StoredCrdtEntry
├── key
├── crdt_type
├── crdt_state
├── state_version
└── causal_context
```

`state_version` tracks causal mutations that changed this key.

`causal_context` tracks causal knowledge associated with the key/session path and may include dots from other keys.

Anti-entropy primarily compares `state_version`; causal read/write validation uses `causal_context`.

## 11. CRDT Common Contract

```python
class CRDT(Protocol):
    def merge(self, other: Self) -> Self: ...
    def to_dict(self) -> dict[str, object]: ...
```

All CRDT merges must be commutative, associative, and idempotent.

## 12. GCounter

State maps actor to non-negative integer component. Mutation increments the local actor's component. Merge uses component-wise maximum. Value is the sum of all components.

## 13. PNCounter

`PNCounter` is composed of positive and negative GCounters. Increment changes the positive side; decrement changes the negative side. Value is `sum(positive) - sum(negative)`.

## 14. ORSet

Phase 4 uses an observed-remove set. For v0.4.0, elements are strings.

```text
adds:
element -> set[Dot]

removed:
set[Dot]
```

Add allocates a new Dot and inserts it into `adds[element]`. Remove moves all currently observed active add dots for the element into `removed`. Merge unions both structures. An unseen concurrent add survives a remove. Tombstone compaction is deferred.

## 15. MVRegister

The multi-value register preserves concurrent writes.

```text
values:
Dot -> deterministic JSON-compatible payload

superseded:
set[Dot]
```

A write supersedes all currently observed visible values, allocates a new Dot, and stores the new value. Merge unions values and superseded dots. Concurrent writes remain visible. A later causally dominant write supersedes them. No physical timestamp chooses a winner.

## 16. CrdtStore

CRDT state is owned by a dedicated in-memory `CrdtStore`.

Responsibilities:

- get entry,
- return immutable snapshot,
- mutate one key atomically,
- merge incoming state,
- enumerate digest entries,
- enforce type consistency.

Per-key operations are serialized with per-key async locking. Different keys may mutate concurrently. `DistributedNode` must not directly own mutable CRDT dictionaries.

## 17. Any-Node Ingress

A client may contact any cluster member.

```text
client
  |
  v
any ingress node
  |
  v
ReplicaSelector(key)
  |
  +-- ingress is authoritative replica --> execute
  |
  +-- ingress is not authoritative ------> single-hop forward
```

The forwarded CRDT request never routes again. Phase-3 TTL remains a secondary loop guard.

## 18. Primary-Less Write Model

Phase 4 uses no permanent leader and no write quorum. Writes are local-first, then asynchronously replicated with bounded retry and eventual anti-entropy repair.

The durability limitation is explicit:

> A locally acknowledged mutation is not durable until another replica learns it. If the only process holding that mutation dies before replication, the mutation can be lost.

## 19. Causally Safe Write Path

A stale replica must not blindly execute an ORSet remove or MVRegister write.

Before mutation, the local `causal_context` must dominate the client token. If not, targeted causal repair runs first. If the requested frontier still cannot be satisfied before the shared deadline, return `CAUSAL_UNAVAILABLE` without mutation.

After causal validation:

1. determine replica set,
2. reserve/coalesce outbox responsibility,
3. reject before mutation if required new slots cannot be reserved,
4. allocate Dot,
5. apply CRDT mutation,
6. update `state_version`,
7. update `causal_context`,
8. commit in-memory state,
9. publish newest snapshots to reserved outbox entries,
10. return success with new CausalToken.

## 20. State-Based Replication

Phase 4 replicates causally complete per-key state rather than raw mutation commands.

Payload contains key, CRDT type, state version, causal context, and typed CRDT state.

Remote handling always merges state. Operation replay is not used.

## 21. Bounded Coalescing Replication Outbox

The outbox key is `(peer_node_id, crdt_key)`.

One pair consumes one pending slot. New mutations for an already pending pair replace the pending state with the newest causally complete snapshot and consume no additional capacity.

Default:

```text
CRDT_REPLICATION_QUEUE_CAPACITY=500
```

If a required new pair cannot be reserved because the outbox is full, return `REPLICATION_BACKPRESSURE` before local mutation.

## 22. Generation-Safe Outbox

Each pending pair has a generation. A worker records the generation it begins sending. If the same pair changes while the send is in flight, the generation increments and the newest state replaces the pending state.

A worker removes the slot only if the current generation still equals the sent generation. Otherwise the pair remains pending and is sent again with the newest snapshot.

## 23. Replication Workers

Defaults:

```text
CRDT_REPLICATION_WORKERS=2
CRDT_REPLICATION_RETRY_MAX_ATTEMPTS=3
CRDT_REPLICATION_RETRY_BASE_DELAY_SECONDS=0.05
CRDT_REPLICATION_RETRY_MAX_DELAY_SECONDS=1.0
```

Fast-path replication retries transport failures with bounded full-jitter retry. Retry exhaustion ends the fast-path attempt; anti-entropy remains responsible for eventual repair. The outbox is not a durable WAL.

## 24. Causal Read A+ Model

A read first checks whether local causal context dominates the client token. If yes, serve immediately.

If not:

1. calculate the missing causal frontier,
2. perform parallel targeted fetches from relevant replicas,
3. merge CRDT states,
4. merge causal proof/context,
5. re-check token dominance,
6. return the causally valid result or `CAUSAL_UNAVAILABLE`.

All repair work consumes the same original request deadline.

## 25. Missing Causal Frontier

`VersionVector.missing_from()` identifies exactly which actor counters are missing relative to a required token and is used for diagnostics and targeted repair planning.

## 26. Causal Read Result

```python
@dataclass(frozen=True, slots=True)
class CausalReadResult:
    key: str
    crdt_type: CrdtType
    value: object
    causal_token: CausalToken
    served_by: str
    repair_performed: bool
```

Successful external responses expose causal status and whether repair was needed.

## 27. Causal Repair Result

```python
@dataclass(frozen=True, slots=True)
class CausalRepairResult:
    satisfied: bool
    merged_version: VersionVector
    contacted_nodes: tuple[str, ...]
    successful_nodes: tuple[str, ...]
```

This separates repair mechanics from node dispatch.

## 28. Cross-Key Causal Sessions

The client token is session-wide. A write to key B may causally depend on a read/write of key A.

A key's `causal_context` may therefore contain dots from other keys. Repair responses may include requested key state plus peer causal frontier proof so causal knowledge can advance without falsely marking unrelated mutations as changes to the requested key.

## 29. Anti-Entropy Strategy

Phase 4 uses digest-driven, replica-aware, selective anti-entropy.

Defaults:

```text
CRDT_ANTI_ENTROPY_INTERVAL_SECONDS=2.0
CRDT_ANTI_ENTROPY_BATCH_SIZE=100
```

Each cycle selects one healthy relevant replica peer.

## 30. Digest Contents

A digest entry contains key, CRDT type, state version, and causal-context summary. No full CRDT payload is sent in the initial digest exchange.

## 31. Digest Comparison

For one key:

```text
state versions equal -> no state transfer
remote dominates     -> fetch remote state
local dominates      -> repair remote peer
concurrent           -> exchange/fetch state, merge, repair peer
```

If state versions are equal but causal contexts differ, metadata may merge without retransmitting full CRDT state.

Version vectors decide whether synchronization is needed; CRDT merge decides how state converges.

## 32. Replica-Aware Anti-Entropy

Only current relevant replica peers synchronize a key. Nodes outside `replicas(key)` are not proactively synchronized for that key.

## 33. Ownership Changes

Old replicas are not immediately deleted after membership/ring changes. They retain a non-authoritative copy that is not actively served or replicated as current ownership. Safe distributed garbage collection is deferred.

## 34. Restart and Rejoin

A restarted node begins with a new Phase-3 incarnation, a new `CausalActor`, and an empty `CrdtStore`.

After membership convergence, anti-entropy reconstructs keys the node should currently replicate.

## 35. Shared Deadline Rule

Phase-3 `REQUEST_TIMEOUT_SECONDS=5` remains authoritative for client CRDT operations.

The same logical deadline covers routing, causal validation, targeted repair, local merge, outbox admission, and remote single-hop forwarding. No stage resets the request budget.

Anti-entropy is independent background work and uses its own bounded peer-operation timeout.

## 36. Protocol Message Types

Existing values 1 through 11 remain unchanged.

Phase 4 adds:

```text
CRDT_MUTATE_REQUEST = 12
CRDT_READ_REQUEST = 13
CRDT_REPLICATE = 14
CRDT_FETCH = 15
CRDT_DIGEST = 16
CRDT_DIGEST_RESPONSE = 17
CRDT_RESPONSE = 18
```

## 37. Error Codes

Existing values 0 through 8 remain unchanged.

Add:

```text
CAUSAL_UNAVAILABLE = 9
REPLICATION_BACKPRESSURE = 10
KEY_NOT_FOUND = 11
```

## 38. Typed Protobuf Causal Model

```proto
message CausalActor {
  string node_id = 1;
  uint64 incarnation = 2;
}

message Dot {
  CausalActor actor = 1;
  uint64 counter = 2;
}

message VersionEntry {
  CausalActor actor = 1;
  uint64 counter = 2;
}

message VersionVector {
  repeated VersionEntry entries = 1;
}

message CausalToken {
  VersionVector version = 1;
}
```

## 39. Typed Protobuf CRDT Type

```proto
enum CrdtType {
  CRDT_TYPE_UNSPECIFIED = 0;
  GCOUNTER = 1;
  PNCOUNTER = 2;
  ORSET = 3;
  MVREGISTER = 4;
}
```

## 40. Typed Mutation Protocol

`CrdtMutationRequest` contains key, causal token, and a `oneof` mutation with increment, decrement, set add, set remove, or register write variants.

Whole-key delete is not part of Phase 4.

## 41. Typed CRDT State Protocol

`CrdtState` contains key, CRDT type, state version, causal context, and a typed state variant for GCounter, PNCounter, ORSet, or MVRegister.

MVRegister user values may use deterministic JSON bytes because they are application data, not causal metadata.

## 42. CrdtClient

Phase-3 `DistributedClient` remains intact. Phase 4 adds `CrdtClient` with increment, decrement, add, remove, register write, and read operations. Every successful operation returns the next session token.

## 43. Node Dispatch

```text
JOIN_REQUEST/PING/PING_REQ/GOSSIP
    -> ClusterService

REQUEST/FORWARDED_REQUEST
    -> existing task path

CRDT_MUTATE_REQUEST/CRDT_READ_REQUEST
    -> CrdtService

CRDT_REPLICATE/CRDT_FETCH/CRDT_DIGEST
    -> ReplicationService
```

CRDT peer/control traffic bypasses the Phase-2 public task token bucket.

## 44. Production File Structure

```text
src/distsys/causal/
├── __init__.py
├── actor.py
├── dot.py
├── version_vector.py
├── token.py
└── clock.py

src/distsys/crdt/
├── __init__.py
├── base.py
├── gcounter.py
├── pncounter.py
├── orset.py
├── mvregister.py
└── types.py

src/distsys/storage/
├── __init__.py
├── models.py
└── crdt_store.py

src/distsys/replication/
├── __init__.py
├── codec.py
├── replica_selector.py
├── outbox.py
├── replicator.py
├── causal_repair.py
├── digest.py
├── anti_entropy.py
└── service.py

src/distsys/crdt_client.py
```

Modified files:

```text
proto/messages.proto
src/distsys/proto/messages_pb2.py
src/distsys/proto/messages_pb2.pyi
src/distsys/protocol/message.py
src/distsys/protocol/codec.py
src/distsys/node.py
src/distsys/utils/config.py
.env.example
Makefile
README.md
docs/PHASES.md
```

Scripts:

```text
scripts/run_phase4_cluster.sh
scripts/phase4_smoke.py
```

## 45. Configuration

```text
CRDT_ENABLED=false
CRDT_REPLICATION_FACTOR=3
CRDT_REPLICATION_QUEUE_CAPACITY=500
CRDT_REPLICATION_WORKERS=2
CRDT_REPLICATION_RETRY_MAX_ATTEMPTS=3
CRDT_REPLICATION_RETRY_BASE_DELAY_SECONDS=0.05
CRDT_REPLICATION_RETRY_MAX_DELAY_SECONDS=1.0
CRDT_ANTI_ENTROPY_INTERVAL_SECONDS=2.0
CRDT_ANTI_ENTROPY_BATCH_SIZE=100
```

Validation:

```text
CRDT_ENABLED=true requires CLUSTER_ENABLED=true
replication factor >= 1
queue capacity >= 1
workers >= 1
retry attempts >= 1
base retry delay >= 0
max retry delay >= base retry delay
anti-entropy interval > 0
anti-entropy batch size >= 1
```

## 46. Logging

Structured events include:

```text
crdt_mutation_applied
crdt_read_served
crdt_replication_reserved
crdt_replication_enqueued
crdt_replication_coalesced
crdt_replication_sent
crdt_replication_failed
crdt_replication_retry_exhausted
causal_repair_started
causal_repair_peer_succeeded
causal_repair_satisfied
causal_read_fast_path
causal_unavailable
anti_entropy_digest_sent
anti_entropy_digest_received
anti_entropy_divergence
anti_entropy_state_fetched
anti_entropy_repaired
crdt_replica_recovered
crdt_replica_non_authoritative
```

Prometheus/Grafana remain deferred.

## 47. Unit Test Map

```text
tests/unit/test_causal_actor.py
tests/unit/test_dot.py
tests/unit/test_version_vector.py
tests/unit/test_causal_token.py
tests/unit/test_causal_clock.py
tests/unit/test_gcounter.py
tests/unit/test_pncounter.py
tests/unit/test_orset.py
tests/unit/test_mvregister.py
tests/unit/test_crdt_store.py
tests/unit/test_replica_selector.py
tests/unit/test_replication_outbox.py
tests/unit/test_replicator.py
tests/unit/test_causal_repair.py
tests/unit/test_digest.py
tests/unit/test_anti_entropy.py
tests/unit/test_crdt_codec.py
tests/unit/test_crdt_config.py
```

Required unit behavior includes actor epoch change, vector dominance/concurrency/missing frontier, merge idempotence, all four CRDT merge semantics, store type safety and atomicity, replica selection, outbox coalescing/capacity/generation safety, bounded retry, causal fast path, targeted repair, and `CAUSAL_UNAVAILABLE`.

## 48. Integration Test Map

```text
tests/integration/test_crdt_local_operations.py
tests/integration/test_crdt_async_replication.py
tests/integration/test_causal_read_repair.py
tests/integration/test_causal_write_repair.py
tests/integration/test_read_your_writes.py
tests/integration/test_monotonic_reads.py
tests/integration/test_writes_follow_reads.py
tests/integration/test_cross_key_causal_session.py
tests/integration/test_orset_concurrent_partition.py
tests/integration/test_mvregister_concurrent_partition.py
tests/integration/test_replication_backpressure.py
tests/integration/test_anti_entropy_convergence.py
tests/integration/test_crdt_node_rejoin.py
tests/integration/test_crdt_replica_reassignment.py
tests/integration/test_crdt_any_node_ingress.py
```

All network integration tests use explicit pytest-assigned ports, never direct `port=0`.

Partition scenarios use an injected peer-transport/fault harness rather than root-only `iptables`.

## 49. Phase-4 Smoke

The three-node smoke must prove:

1. Phase-3 membership convergence,
2. GCounter mutation,
3. remote read through another ingress,
4. replication to current replica set,
5. ORSet mutation,
6. stale-replica causal read,
7. targeted causal repair,
8. `repair_performed=true`,
9. deterministic MVRegister concurrent merge scenario,
10. one-node stop,
11. continued valid writes with reduced effective RF,
12. restart with empty store,
13. new membership incarnation and CausalActor,
14. anti-entropy reconstruction,
15. final active-replica convergence.

## 50. Non-Goals

Phase 4 excludes:

- durable WAL,
- disk-backed CRDT persistence,
- write quorum,
- read quorum,
- consensus,
- permanent leader,
- exactly-once execution,
- multi-key transactions,
- atomic multi-key mutation,
- whole-key delete,
- causal tombstone garbage collection,
- delta-CRDT protocol,
- operation-based CRDT protocol,
- Merkle tree,
- hinted handoff,
- sloppy quorum,
- durable deduplication,
- Prometheus/Grafana,
- new TLS/mTLS functionality.

## 51. Delivery Semantics

Phase 4 guarantees:

> Primary-less causal session consistency and eventual CRDT convergence for state retained by at least one replica, using best-effort asynchronous replication, bounded retry, targeted causal repair, and anti-entropy.

It does not claim durable acknowledgement, quorum durability, exactly-once execution, or transaction semantics.

## 52. Phase-4 Exit Criteria

### Causal Metadata

- [ ] CausalActor includes Phase-3 incarnation.
- [ ] Restart cannot reuse old Dot identity.
- [ ] VersionVector merge is correct.
- [ ] VersionVector dominance works.
- [ ] VersionVector concurrency works.
- [ ] Missing frontier calculation works.
- [ ] Session-wide CausalToken round-trips through Protobuf.

### CRDT Core

- [ ] GCounter increments and converges.
- [ ] PNCounter increments/decrements and converges.
- [ ] ORSet implements observed-remove semantics.
- [ ] Unseen concurrent ORSet add survives remove.
- [ ] MVRegister preserves concurrent writes.
- [ ] Later causally dominant MVRegister write supersedes concurrent values.
- [ ] Duplicate state merges are harmless.

### Replica Placement

- [ ] Phase-3 consistent-hash candidate order is reused.
- [ ] RF defaults to 3.
- [ ] Effective RF contracts with available ALIVE nodes.
- [ ] SUSPECT and DEAD nodes are excluded.
- [ ] Any-node ingress routes to an authoritative replica.
- [ ] Forwarded CRDT request never reroutes twice.

### Write Path

- [ ] Incoming token is validated.
- [ ] Stale writer performs causal repair before mutation.
- [ ] Unique Dot is allocated.
- [ ] Outbox capacity is reserved before mutation.
- [ ] Full new outbox pair rejects with REPLICATION_BACKPRESSURE.
- [ ] Rejected write leaves CRDT state unchanged.
- [ ] Same pending peer/key coalesces.
- [ ] Local state commits before client success.
- [ ] Response carries updated CausalToken.

### Async Replication

- [ ] State snapshots, not operations, are replicated.
- [ ] Two workers are used by default.
- [ ] Retries are bounded.
- [ ] Duplicate and reordered snapshots merge safely.
- [ ] In-flight older generation cannot discard newer state.
- [ ] Retry exhaustion leaves anti-entropy responsible.

### Causal Reads

- [ ] Local fast path works.
- [ ] Token dominance is enforced.
- [ ] Missing frontier is calculated.
- [ ] Remote repair fetches run in parallel.
- [ ] CRDT states merge locally.
- [ ] Causal proof/context merges.
- [ ] Successful repair returns `repair_performed=true`.
- [ ] Unsatisfied frontier returns CAUSAL_UNAVAILABLE.
- [ ] Missing key returns KEY_NOT_FOUND.
- [ ] Original request deadline is never reset.

### Session Consistency

- [ ] Read-your-writes is demonstrated.
- [ ] Monotonic reads are demonstrated.
- [ ] Monotonic writes are demonstrated.
- [ ] Writes-follow-reads is demonstrated.
- [ ] Cross-key session dependency is demonstrated.

### Anti-Entropy

- [ ] Digest contains key/type/state version/context.
- [ ] Equal state skips transfer.
- [ ] Remote-ahead state is fetched.
- [ ] Local-ahead state repairs peer.
- [ ] Concurrent state is merged.
- [ ] Only divergent keys transfer full state.
- [ ] Only relevant replica peers synchronize.
- [ ] One peer per cycle is used by default.
- [ ] Batch limit works.

### Failure and Recovery

- [ ] Writes continue with reduced effective RF.
- [ ] Rejoined node starts with empty store.
- [ ] Rejoined node receives a new causal actor epoch.
- [ ] Anti-entropy restores assigned keys.
- [ ] Stale incarnation cannot collide with new Dots.
- [ ] Old non-authoritative copies are not actively served.
- [ ] Old copies are not eagerly deleted.

### Compatibility

- [ ] Phase-1 tests remain green.
- [ ] Phase-2 tests remain green.
- [ ] Phase-3 tests remain green.
- [ ] Cluster-disabled behavior remains unchanged.
- [ ] `CRDT_ENABLED` defaults to false.
- [ ] Existing MessageType values 1 through 11 remain unchanged.
- [ ] Existing ErrorCode values 0 through 8 remain unchanged.

### Quality

- [ ] Full pytest suite passes.
- [ ] Ruff passes.
- [ ] Black passes.
- [ ] mypy passes.
- [ ] Protobuf regenerates cleanly.
- [ ] compileall passes.
- [ ] Three-node Phase-4 smoke passes.
- [ ] Managed node failure/rejoin smoke passes.
- [ ] Documentation states durability limitation accurately.

Only after all exit criteria pass may `v0.4.0` be created.
