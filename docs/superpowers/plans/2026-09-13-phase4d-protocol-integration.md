# Phase 4D Protocol, Client, Node Integration, and Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Phase-4 causal CRDT behavior over typed Protobuf, integrate it into DistributedNode, add CrdtClient, and prove all session/convergence/rejoin guarantees end to end.

**Architecture:** Typed protocol messages carry causal metadata and CRDT states. CrdtService orchestrates causal repair, outbox admission, local mutation/read, and single-hop ingress forwarding while DistributedNode remains the top-level dispatch/lifecycle owner.

**Tech Stack:** Python 3.12+, asyncio TCP framing, Protobuf, Phase-3 cluster transport, Phase-4 causal/CRDT/replication modules, pytest.

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

Create:

```text
src/distsys/replication/codec.py
src/distsys/crdt_service.py
src/distsys/crdt_client.py
scripts/run_phase4_cluster.sh
scripts/phase4_smoke.py
```

Modify:

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

### Task 1: MessageType and Protobuf schema

**Files:**
- Modify: `src/distsys/protocol/message.py`
- Modify: `proto/messages.proto`
- Generate: `src/distsys/proto/messages_pb2.py`
- Generate: `src/distsys/proto/messages_pb2.pyi`
- Test: `tests/unit/test_message.py`
- Test: `tests/unit/test_crdt_codec.py`

**Interfaces:**
- New MessageTypes exactly 12-18
- New ErrorCodes exactly 9-11
- Typed causal and CRDT messages from the approved spec

- [ ] **Step 1: Add numeric-stability tests for old and new MessageType values**
- [ ] **Step 2: Append MessageType 12-18**
- [ ] **Step 3: Append ErrorCode 9-11**
- [ ] **Step 4: Add CausalActor/Dot/VersionVector/CausalToken Protobuf messages**
- [ ] **Step 5: Add CrdtType and typed state messages**
- [ ] **Step 6: Add mutation/read/response/replicate/fetch/digest messages**
- [ ] **Step 7: Regenerate**

```bash
make proto
```

- [ ] **Step 8: Verify old numbers were not changed**

```bash
grep -nE 'PEER_UNAVAILABLE = 8|CAUSAL_UNAVAILABLE = 9|REPLICATION_BACKPRESSURE = 10|KEY_NOT_FOUND = 11' proto/messages.proto
```

- [ ] **Step 9: Commit**

```bash
git add proto src/distsys/proto src/distsys/protocol/message.py tests/unit/test_message.py
git commit -m "feat: add typed causal crdt wire schema"
```

### Task 2: Phase-4 codec

**Files:**
- Create: `src/distsys/replication/codec.py`
- Test: `tests/unit/test_crdt_codec.py`

**Interfaces:**
- Explicit converters for actor, dot, vector, token, CRDT states, stored entries, digests, and mutation payloads

- [ ] **Step 1: Write actor/dot/vector/token round-trip tests**
- [ ] **Step 2: Write GCounter/PNCounter/ORSet/MVRegister state round-trip tests**
- [ ] **Step 3: Write malformed/unspecified enum rejection tests**
- [ ] **Step 4: Run failure**
- [ ] **Step 5: Implement explicit converters; never pickle**
- [ ] **Step 6: Run and commit**

```bash
python -m pytest -q tests/unit/test_crdt_codec.py
git add src/distsys/replication/codec.py tests/unit/test_crdt_codec.py
git commit -m "feat: add crdt protobuf codecs"
```

### Task 3: CRDT settings

**Files:**
- Modify: `src/distsys/utils/config.py`
- Modify: `.env.example`
- Test: `tests/unit/test_crdt_config.py`

**Interfaces:**
- Settings fields and validation from the approved spec

- [ ] **Step 1: Test exact defaults**
- [ ] **Step 2: Test `CRDT_ENABLED=true` requires clustering**
- [ ] **Step 3: Test RF/capacity/workers/retry/interval/batch lower bounds**
- [ ] **Step 4: Implement using existing Settings conventions**
- [ ] **Step 5: Update `.env.example`**
- [ ] **Step 6: Run and commit**

```bash
python -m pytest -q tests/unit/test_crdt_config.py
git add src/distsys/utils/config.py .env.example tests/unit/test_crdt_config.py
git commit -m "feat: configure causal crdt services"
```

### Task 4: CrdtService

**Files:**
- Create: `src/distsys/crdt_service.py`
- Test: `tests/integration/test_crdt_local_operations.py`

**Interfaces:**
- `mutate(request, deadline, forwarded=False) -> CrdtOperationResult`
- `read(request, deadline, forwarded=False) -> CausalReadResult`

- [ ] **Step 1: Write local GCounter/PNCounter/ORSet/MVRegister tests**
- [ ] **Step 2: Write KEY_NOT_FOUND test**
- [ ] **Step 3: Write stale-token mutation test**
- [ ] **Step 4: Implement mutation order exactly**

```text
validate
causal repair if needed
replica selection
outbox reserve
key lock
allocate dot
apply mutation
update state_version
update causal_context
commit
publish outbox
return token
```

- [ ] **Step 5: Implement local causal read fast path**
- [ ] **Step 6: Run and commit**

```bash
python -m pytest -q tests/integration/test_crdt_local_operations.py
git add src/distsys/crdt_service.py tests/integration/test_crdt_local_operations.py
git commit -m "feat: add causal crdt service"
```

### Task 5: Real Phase-4 peer transport and node dispatch

**Files:**
- Modify: `src/distsys/cluster/peer_client.py` or create a focused Phase-4 peer adapter beside it
- Modify: `src/distsys/node.py`
- Test: `tests/integration/test_crdt_async_replication.py`

**Interfaces:**
- Implement 4C peer protocols using one-shot framed TCP
- Dispatch CRDT_MUTATE/READ/REPLICATE/FETCH/DIGEST before public task rate limiting

- [ ] **Step 1: Write 3-node async replication test with explicit pytest ports**
- [ ] **Step 2: Implement CRDT_REPLICATE exchange**
- [ ] **Step 3: Implement CRDT_FETCH exchange**
- [ ] **Step 4: Implement CRDT_DIGEST exchange**
- [ ] **Step 5: Initialize Phase-4 services only when enabled**

Startup order:
1. executor,
2. server bind,
3. Phase-3 local member/cluster,
4. causal actor from membership incarnation,
5. clock/store/replication/CrdtService,
6. cluster bootstrap,
7. start Phase-4 background workers.

Shutdown stops Phase-4 background tasks before final transport/executor teardown.

- [ ] **Step 6: Test CRDT-disabled messages return structured INVALID_REQUEST**
- [ ] **Step 7: Run and commit**

```bash
python -m pytest -q tests/integration/test_crdt_async_replication.py
git add src/distsys/cluster src/distsys/node.py tests/integration/test_crdt_async_replication.py
git commit -m "feat: integrate crdt peer protocol"
```

### Task 6: CrdtClient and any-node ingress

**Files:**
- Create: `src/distsys/crdt_client.py`
- Test: `tests/integration/test_crdt_any_node_ingress.py`

**Interfaces:**
- `increment`
- `decrement`
- `add`
- `remove`
- `write_register`
- `read`
- optional `causal_token` on every call

- [ ] **Step 1: Write a key whose owner/replica does not include ingress first**
- [ ] **Step 2: Send mutation through non-replica ingress**
- [ ] **Step 3: Assert single-hop forwarding and correct `served_by`**
- [ ] **Step 4: Implement client encode/decode and server forwarded guard**
- [ ] **Step 5: Run and commit**

```bash
python -m pytest -q tests/integration/test_crdt_any_node_ingress.py
git add src/distsys/crdt_client.py src/distsys/crdt_service.py tests/integration/test_crdt_any_node_ingress.py
git commit -m "feat: add topology transparent crdt client"
```

### Task 7: Causal session guarantees

**Files:**
- Create:
  - `tests/integration/test_causal_read_repair.py`
  - `tests/integration/test_causal_write_repair.py`
  - `tests/integration/test_read_your_writes.py`
  - `tests/integration/test_monotonic_reads.py`
  - `tests/integration/test_writes_follow_reads.py`
  - `tests/integration/test_cross_key_causal_session.py`

**Interfaces:**
- Verifies public CrdtClient semantics

- [ ] **Step 1: Read-your-writes across replicas**
- [ ] **Step 2: Monotonic-read replica switch**
- [ ] **Step 3: Monotonic writes**
- [ ] **Step 4: Writes-follow-reads**
- [ ] **Step 5: Cross-key A->B dependency**
- [ ] **Step 6: Read repair returns `repair_performed=True`**
- [ ] **Step 7: Stale writer repairs before ORSet/MVRegister mutation**
- [ ] **Step 8: Fault peers so required frontier cannot be reached; assert CAUSAL_UNAVAILABLE**
- [ ] **Step 9: Run and commit**

```bash
python -m pytest -q \
  tests/integration/test_causal_read_repair.py \
  tests/integration/test_causal_write_repair.py \
  tests/integration/test_read_your_writes.py \
  tests/integration/test_monotonic_reads.py \
  tests/integration/test_writes_follow_reads.py \
  tests/integration/test_cross_key_causal_session.py
git add tests/integration
git commit -m "test: verify causal session guarantees"
```

### Task 8: Partition, backpressure, and anti-entropy tests

**Files:**
- Create:
  - `tests/integration/test_orset_concurrent_partition.py`
  - `tests/integration/test_mvregister_concurrent_partition.py`
  - `tests/integration/test_replication_backpressure.py`
  - `tests/integration/test_anti_entropy_convergence.py`

**Interfaces:**
- Uses injected test fault transport; no root/iptables requirement

- [ ] **Step 1: Block selected Phase-4 peer traffic with a deterministic test harness**
- [ ] **Step 2: ORSet remove vs unseen concurrent add; heal; assert add survives**
- [ ] **Step 3: MVRegister concurrent writes; heal; assert both survive**
- [ ] **Step 4: Resolve MVRegister using merged token; assert one resolution value**
- [ ] **Step 5: Fill outbox and prove rejected write leaves local state unchanged**
- [ ] **Step 6: Diverge one of two keys; prove anti-entropy transfers full state only for divergent key**
- [ ] **Step 7: Run and commit**

```bash
python -m pytest -q \
  tests/integration/test_orset_concurrent_partition.py \
  tests/integration/test_mvregister_concurrent_partition.py \
  tests/integration/test_replication_backpressure.py \
  tests/integration/test_anti_entropy_convergence.py
git add tests/integration
git commit -m "test: verify crdt partition convergence"
```

### Task 9: Rejoin and reassignment

**Files:**
- Create:
  - `tests/integration/test_crdt_node_rejoin.py`
  - `tests/integration/test_crdt_replica_reassignment.py`

**Interfaces:**
- Verifies empty-store restart, new actor epoch, reconstruction, non-authoritative old replicas

- [ ] **Step 1: Capture old incarnation/actor**
- [ ] **Step 2: Stop node, continue writes, restart same node_id**
- [ ] **Step 3: Assert new incarnation/actor and empty initial store**
- [ ] **Step 4: Run anti-entropy and assert assigned state reconstructed**
- [ ] **Step 5: Change membership so replica set moves**
- [ ] **Step 6: Assert new replica receives state and old replica is not authoritative**
- [ ] **Step 7: Run and commit**

```bash
python -m pytest -q \
  tests/integration/test_crdt_node_rejoin.py \
  tests/integration/test_crdt_replica_reassignment.py
git add tests/integration
git commit -m "test: verify crdt rejoin and reassignment"
```

### Task 10: Phase-4 smoke, Makefile, and documentation

**Files:**
- Create: `scripts/run_phase4_cluster.sh`
- Create: `scripts/phase4_smoke.py`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `docs/PHASES.md`

**Interfaces:**
- `make phase4-cluster`
- `make phase4-smoke`

- [ ] **Step 1: Implement safe three-node launcher**

Use ports 18000/18001/18002, trap cleanup, PID ownership, preflight port checks, `CPU_WORKERS=1`, CRDT enabled.

- [ ] **Step 2: Implement normal smoke**

Prove:
- membership convergence,
- GCounter replication,
- stale-replica causal repair,
- `repair_performed=true`,
- ORSet/MVRegister behavior,
- final authoritative convergence.

- [ ] **Step 3: Implement managed failure/rejoin smoke**

Only kill/restart child processes launched by the managed command. Prove reduced-RF write, new actor epoch, anti-entropy reconstruction.

- [ ] **Step 4: Add Makefile targets**
- [ ] **Step 5: Document guarantees and limitations accurately**
- [ ] **Step 6: Run full gate**

```bash
make proto
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
```

- [ ] **Step 7: Run both normal and managed smoke**
- [ ] **Step 8: Check cleanup**

```bash
for port in 18000 18001 18002; do
  ss -ltnp | grep ":$port" || echo "Port $port is free"
done
```

- [ ] **Step 9: Commit**

```bash
git add scripts Makefile README.md docs
git commit -m "docs: complete phase four causal crdt release"
```
