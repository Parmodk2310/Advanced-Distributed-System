# Phase 3 Distributed Cluster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the verified `v0.2.0` single-node runtime into a three-node decentralized cluster with static-seed bootstrap, SWIM-lite membership/failure detection, gossip convergence, SHA-256 consistent-hash routing, single-hop forwarding, transport-only retry/circuit breaking, deterministic failover, and clean node rejoin.

**Architecture:** Each node keeps the existing framed asyncio TCP server and Protobuf envelope. Cluster control traffic (`JOIN_REQUEST`, `PING`, `ACK`, `PING_REQ`, `GOSSIP`) shares that endpoint but bypasses public task rate limiting/backpressure; keyed task traffic uses a consistent-hash ring and forwards at most one hop through `PeerClient`. Membership is decentralized and versioned by incarnation; `MembershipTable` owns merge/tombstone rules, `FailureDetector` owns suspicion, `GossipLoop` owns best-effort dissemination, and `ClusterService` wires them into `DistributedNode`.

**Tech Stack:** Python 3.12+, `asyncio`, Protobuf / `grpcio-tools`, SHA-256, `pytest`, `pytest-asyncio`, Ruff, Black, mypy.

**Spec:** `docs/superpowers/specs/2026-09-13-phase3-distributed-cluster-design.md`

## Global Constraints

- Base release is `v0.2.0`; implementation branch is `phase/3-distributed-cluster`.
- Preserve protocol version `1` and the fixed 8-byte frame header.
- Preserve existing numeric message types: `REQUEST=1`, `RESPONSE=2`, `ERROR=3`, `HEARTBEAT=4`.
- Preserve existing error-code values `0..6`; Phase 3 adds `NO_ROUTE=7`, `PEER_UNAVAILABLE=8`.
- Preserve Phase-2 task contracts for `echo`, `hash`, `sort`, and `aggregate`.
- `CLUSTER_ENABLED=false` remains the default; standalone Phase-2 behavior must remain unchanged.
- New network integration tests use `unused_tcp_port_factory`; do not use `port=0` in new Phase-3 integration tests.
- Cluster control traffic bypasses the public task token bucket and local execution backpressure.
- Forwarded requests bypass the public token bucket but still obey destination-node backpressure and deadline.
- Forwarded requests never route again; routing is at most one hop from ingress to selected owner/failover candidate.
- Task retry applies only to transport/protocol failures; structured application errors are decoded outside the task circuit breaker.
- Failure-detector control traffic does not use task retry/circuit breakers; direct + indirect probes provide resilience.
- Only `ALIVE` members participate in the hash ring; `SUSPECT` and `DEAD` are excluded immediately from new ownership.
- Delivery semantics are best-effort/idempotent; do not claim exactly-once execution.
- Keep three-node laptop defaults conservative: `CPU_WORKERS=1`, `CPU_QUEUE_CAPACITY=100` per node.
- Do not add etcd, CRDTs, vector clocks, TLS/mTLS, Prometheus/Grafana, Kubernetes, Terraform, or persistent membership in Phase 3.

---

## Execution Order

1. Verify the `v0.2.0` baseline and branch state.
2. Add cluster domain types and seed parsing.
3. Add membership merge/refutation/tombstone state machine.
4. Extend Protobuf/message types and add cluster codecs plus routed task payloads.
5. Add deterministic consistent hashing.
6. Add cluster configuration and validation.
7. Add the diagnostic `cluster.whoami` task.
8. Add peer control/task transport with retry and per-peer circuit breakers.
9. Add keyed cluster routing and failover rules.
10. Add SWIM-lite failure detection.
11. Add periodic gossip.
12. Add `ClusterService` bootstrap/control/lifecycle coordination.
13. Integrate cluster dispatch into `DistributedNode` and routed-key support into `DistributedClient`.
14. Add three-node integration coverage for join, gossip, failure, routing, failover, and rejoin.
15. Add smoke/cluster-run scripts and documentation.
16. Run complete Phase-1/2/3 verification and prepare `v0.3.0` only after all gates are green.

## Pre-flight: Freeze the Baseline

Run before Task 1:

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate

git branch --show-current
git status --short
git merge-base --is-ancestor v0.2.0 HEAD
make quality
```

Expected:

```text
phase/3-distributed-cluster
<no git status output>
54 passed
All checks passed!
Black reports all files unchanged
Success: no issues found in 27 source files
```

If the branch is not `phase/3-distributed-cluster`, the working tree is not clean, `v0.2.0` is not an ancestor, or the baseline quality gate fails, stop before changing production code.

---
### Task 1: Cluster Domain Types and Seed Parsing

**Files:**
- Create: `src/distsys/cluster/__init__.py`
- Create: `src/distsys/cluster/member.py`
- Create: `tests/unit/test_member.py`

**Interfaces:**
- Produces: `MemberStatus(IntEnum)` with `ALIVE=1`, `SUSPECT=2`, `DEAD=3`.
- Produces: immutable `ClusterMember(node_id, host, port, status, incarnation)`.
- Produces: immutable `SeedAddress(host, port)` with `SeedAddress.parse(raw: str) -> SeedAddress`.
- Produces: `fresh_incarnation() -> int` using `time.time_ns()`.
- Consumed later by membership, codecs, hashing, peer networking, configuration, and cluster service.

- [ ] **Step 1: Write the failing domain tests**

Create `tests/unit/test_member.py`:

```python
import pytest

from distsys.cluster.member import (
    ClusterMember,
    MemberStatus,
    SeedAddress,
    fresh_incarnation,
)


def test_member_status_severity_order_is_stable():
    assert MemberStatus.ALIVE < MemberStatus.SUSPECT < MemberStatus.DEAD


def test_cluster_member_is_immutable():
    member = ClusterMember(
        node_id="node-1",
        host="127.0.0.1",
        port=18001,
        status=MemberStatus.ALIVE,
        incarnation=10,
    )
    with pytest.raises(AttributeError):
        member.status = MemberStatus.DEAD  # type: ignore[misc]


def test_seed_address_parses_host_and_port():
    assert SeedAddress.parse("127.0.0.1:18000") == SeedAddress(
        host="127.0.0.1", port=18000
    )


@pytest.mark.parametrize(
    "raw",
    ["", "127.0.0.1", ":18000", "host:0", "host:65536", "host:not-a-port"],
)
def test_seed_address_rejects_invalid_values(raw: str):
    with pytest.raises(ValueError):
        SeedAddress.parse(raw)


def test_fresh_incarnation_is_positive_and_increases():
    first = fresh_incarnation()
    second = fresh_incarnation()
    assert first > 0
    assert second >= first
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python -m pytest -q tests/unit/test_member.py
```

Expected: collection/import failure because `distsys.cluster.member` does not exist yet.

- [ ] **Step 3: Implement the domain model**

Create `src/distsys/cluster/__init__.py` as an empty package marker and create `src/distsys/cluster/member.py`:

```python
"""Cluster membership domain types."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum


class MemberStatus(IntEnum):
    ALIVE = 1
    SUSPECT = 2
    DEAD = 3


@dataclass(slots=True, frozen=True)
class ClusterMember:
    node_id: str
    host: str
    port: int
    status: MemberStatus
    incarnation: int

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id is required")
        if not self.host:
            raise ValueError("host is required")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.incarnation < 1:
            raise ValueError("incarnation must be positive")


@dataclass(slots=True, frozen=True)
class SeedAddress:
    host: str
    port: int

    @classmethod
    def parse(cls, raw: str) -> SeedAddress:
        value = raw.strip()
        if not value or ":" not in value:
            raise ValueError(f"invalid seed address: {raw!r}")
        host, raw_port = value.rsplit(":", 1)
        host = host.strip()
        if not host:
            raise ValueError("seed host is required")
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ValueError(f"invalid seed port: {raw_port!r}") from exc
        if not 1 <= port <= 65535:
            raise ValueError("seed port must be between 1 and 65535")
        return cls(host=host, port=port)


def fresh_incarnation() -> int:
    return time.time_ns()
```

- [ ] **Step 4: Verify GREEN**

```bash
python -m pytest -q tests/unit/test_member.py
python -m ruff check src/distsys/cluster/member.py tests/unit/test_member.py
python -m mypy src/distsys/cluster/member.py
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```bash
git add src/distsys/cluster tests/unit/test_member.py
git commit -m "feat: add cluster membership domain types"
```

---

### Task 2: Membership Table, Incarnation Merge Rules, Self-Refutation, and Tombstones

**Files:**
- Create: `src/distsys/cluster/membership.py`
- Create: `tests/unit/test_membership.py`

**Interfaces:**
- Consumes: `ClusterMember`, `MemberStatus` from Task 1.
- Produces: `MembershipTable` with asynchronous atomic operations:
  - `snapshot() -> tuple[ClusterMember, ...]`
  - `get(node_id: str) -> ClusterMember | None`
  - `alive_members(*, include_self: bool = True) -> tuple[ClusterMember, ...]`
  - `probe_candidates() -> tuple[ClusterMember, ...]`
  - `merge(records: Iterable[ClusterMember]) -> bool`
  - `mark_suspect(node_id: str) -> bool`
  - `advance_timeouts_and_purge() -> bool`
- Produces: monotonic `version` that increments whenever stored membership/tombstone state changes.
- Later `ClusterService` rebuilds the ring when this version changes.

- [ ] **Step 1: Write failing merge/state-machine tests**

Create `tests/unit/test_membership.py`:

```python
import pytest

from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.membership import MembershipTable


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def member(
    node_id: str,
    *,
    incarnation: int,
    status: MemberStatus = MemberStatus.ALIVE,
    port: int = 18000,
) -> ClusterMember:
    return ClusterMember(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        status=status,
        incarnation=incarnation,
    )


@pytest.mark.asyncio
async def test_higher_incarnation_replaces_complete_member_record():
    clock = FakeClock()
    table = MembershipTable(
        member("node-0", incarnation=100),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([member("node-1", incarnation=10, port=18001)])
    changed = await table.merge(
        [member("node-1", incarnation=11, status=MemberStatus.ALIVE, port=19001)]
    )
    assert changed is True
    assert await table.get("node-1") == member(
        "node-1", incarnation=11, status=MemberStatus.ALIVE, port=19001
    )


@pytest.mark.asyncio
async def test_stale_incarnation_is_ignored():
    clock = FakeClock()
    table = MembershipTable(
        member("node-0", incarnation=100),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([member("node-1", incarnation=20, port=18001)])
    changed = await table.merge(
        [member("node-1", incarnation=19, status=MemberStatus.DEAD, port=19001)]
    )
    assert changed is False
    assert (await table.get("node-1")).incarnation == 20  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_equal_incarnation_more_severe_status_wins_without_address_change():
    clock = FakeClock()
    table = MembershipTable(
        member("node-0", incarnation=100),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([member("node-1", incarnation=20, port=18001)])
    await table.merge(
        [member("node-1", incarnation=20, status=MemberStatus.SUSPECT, port=19001)]
    )
    stored = await table.get("node-1")
    assert stored == member(
        "node-1", incarnation=20, status=MemberStatus.SUSPECT, port=18001
    )


@pytest.mark.asyncio
async def test_local_suspicion_self_refutes_with_newer_alive_incarnation():
    clock = FakeClock()
    table = MembershipTable(
        member("node-0", incarnation=100),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge(
        [member("node-0", incarnation=100, status=MemberStatus.SUSPECT)]
    )
    local = await table.get("node-0")
    assert local == member("node-0", incarnation=101, status=MemberStatus.ALIVE)


@pytest.mark.asyncio
async def test_suspect_becomes_dead_then_tombstone_blocks_stale_resurrection():
    clock = FakeClock()
    table = MembershipTable(
        member("node-0", incarnation=100),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([member("node-1", incarnation=20, port=18001)])
    assert await table.mark_suspect("node-1") is True
    clock.advance(3.1)
    assert await table.advance_timeouts_and_purge() is True
    assert (await table.get("node-1")).status is MemberStatus.DEAD  # type: ignore[union-attr]

    changed = await table.merge([member("node-1", incarnation=20, port=18001)])
    assert changed is False
    assert (await table.get("node-1")).status is MemberStatus.DEAD  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_dead_tombstone_is_purged_after_retention():
    clock = FakeClock()
    table = MembershipTable(
        member("node-0", incarnation=100),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge(
        [member("node-1", incarnation=20, status=MemberStatus.DEAD, port=18001)]
    )
    clock.advance(30.1)
    assert await table.advance_timeouts_and_purge() is True
    assert await table.get("node-1") is None
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/unit/test_membership.py
```

Expected: import failure because `MembershipTable` does not exist.

- [ ] **Step 3: Implement `MembershipTable` minimally but completely for the tested rules**

Create `src/distsys/cluster/membership.py` with these exact public signatures and state rules:

```python
"""Atomic cluster membership state and SWIM-style merge rules."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable
from dataclasses import replace

from distsys.cluster.member import ClusterMember, MemberStatus


class MembershipTable:
    def __init__(
        self,
        local_member: ClusterMember,
        *,
        suspicion_timeout_seconds: float,
        dead_retention_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.local_node_id = local_member.node_id
        self.suspicion_timeout_seconds = suspicion_timeout_seconds
        self.dead_retention_seconds = dead_retention_seconds
        self._clock = clock
        self._members: dict[str, ClusterMember] = {local_member.node_id: local_member}
        self._suspected_at: dict[str, float] = {}
        self._dead_at: dict[str, float] = {}
        self._version = 1
        self._lock = asyncio.Lock()

    @property
    def version(self) -> int:
        return self._version

    async def snapshot(self) -> tuple[ClusterMember, ...]:
        async with self._lock:
            return tuple(self._members[key] for key in sorted(self._members))

    async def get(self, node_id: str) -> ClusterMember | None:
        async with self._lock:
            return self._members.get(node_id)

    async def alive_members(self, *, include_self: bool = True) -> tuple[ClusterMember, ...]:
        async with self._lock:
            return tuple(
                member
                for node_id, member in sorted(self._members.items())
                if member.status is MemberStatus.ALIVE
                and (include_self or node_id != self.local_node_id)
            )

    async def probe_candidates(self) -> tuple[ClusterMember, ...]:
        async with self._lock:
            return tuple(
                member
                for node_id, member in sorted(self._members.items())
                if node_id != self.local_node_id
                and member.status in (MemberStatus.ALIVE, MemberStatus.SUSPECT)
            )

    def _record_timer_state(self, member: ClusterMember) -> None:
        now = self._clock()
        if member.status is MemberStatus.ALIVE:
            self._suspected_at.pop(member.node_id, None)
            self._dead_at.pop(member.node_id, None)
        elif member.status is MemberStatus.SUSPECT:
            self._suspected_at.setdefault(member.node_id, now)
            self._dead_at.pop(member.node_id, None)
        else:
            self._suspected_at.pop(member.node_id, None)
            self._dead_at.setdefault(member.node_id, now)

    def _merge_one_locked(self, incoming: ClusterMember) -> bool:
        current = self._members.get(incoming.node_id)

        if incoming.node_id == self.local_node_id:
            assert current is not None
            if (
                incoming.status in (MemberStatus.SUSPECT, MemberStatus.DEAD)
                and incoming.incarnation >= current.incarnation
            ):
                self._members[self.local_node_id] = replace(
                    current,
                    status=MemberStatus.ALIVE,
                    incarnation=incoming.incarnation + 1,
                )
                self._record_timer_state(self._members[self.local_node_id])
                return True
            return False

        if current is None:
            self._members[incoming.node_id] = incoming
            self._record_timer_state(incoming)
            return True

        if incoming.incarnation < current.incarnation:
            return False

        if incoming.incarnation > current.incarnation:
            self._members[incoming.node_id] = incoming
            self._record_timer_state(incoming)
            return True

        if incoming.status > current.status:
            updated = replace(current, status=incoming.status)
            self._members[incoming.node_id] = updated
            self._record_timer_state(updated)
            return True

        return False

    async def merge(self, records: Iterable[ClusterMember]) -> bool:
        async with self._lock:
            changed = False
            for record in records:
                changed = self._merge_one_locked(record) or changed
            if changed:
                self._version += 1
            return changed

    async def mark_suspect(self, node_id: str) -> bool:
        async with self._lock:
            current = self._members.get(node_id)
            if current is None or node_id == self.local_node_id:
                return False
            if current.status is not MemberStatus.ALIVE:
                return False
            updated = replace(current, status=MemberStatus.SUSPECT)
            self._members[node_id] = updated
            self._record_timer_state(updated)
            self._version += 1
            return True

    async def advance_timeouts_and_purge(self) -> bool:
        async with self._lock:
            now = self._clock()
            changed = False

            for node_id, suspected_at in list(self._suspected_at.items()):
                member = self._members.get(node_id)
                if member is None or member.status is not MemberStatus.SUSPECT:
                    self._suspected_at.pop(node_id, None)
                    continue
                if now - suspected_at >= self.suspicion_timeout_seconds:
                    updated = replace(member, status=MemberStatus.DEAD)
                    self._members[node_id] = updated
                    self._suspected_at.pop(node_id, None)
                    self._dead_at[node_id] = now
                    changed = True

            for node_id, dead_at in list(self._dead_at.items()):
                if node_id == self.local_node_id:
                    continue
                member = self._members.get(node_id)
                if member is None or member.status is not MemberStatus.DEAD:
                    self._dead_at.pop(node_id, None)
                    continue
                if now - dead_at >= self.dead_retention_seconds:
                    self._members.pop(node_id, None)
                    self._dead_at.pop(node_id, None)
                    changed = True

            if changed:
                self._version += 1
            return changed
```

- [ ] **Step 4: Verify GREEN and regression safety**

```bash
python -m pytest -q tests/unit/test_member.py tests/unit/test_membership.py
python -m ruff check src/distsys/cluster tests/unit/test_member.py tests/unit/test_membership.py
python -m mypy src/distsys/cluster
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/distsys/cluster/membership.py tests/unit/test_membership.py
git commit -m "feat: add incarnation-aware membership table"
```

---
### Task 3: Protocol Schema, Message Types, Routed Task Payload, and Cluster Codecs

**Files:**
- Modify: `proto/messages.proto`
- Modify: `src/distsys/protocol/message.py`
- Modify: `src/distsys/protocol/codec.py`
- Create: `src/distsys/cluster/codec.py`
- Modify/regenerate: `src/distsys/proto/messages_pb2.py`
- Modify/regenerate: `src/distsys/proto/messages_pb2.pyi`
- Modify: `tests/unit/test_message.py`
- Modify: `tests/unit/test_codec.py`
- Create: `tests/unit/test_cluster_codec.py`
- Modify: `Makefile` only if the existing `proto` target no longer regenerates both generated files correctly; otherwise leave it unchanged.

**Interfaces:**
- `MessageType` adds `JOIN_REQUEST=5`, `JOIN_RESPONSE=6`, `PING=7`, `ACK=8`, `PING_REQ=9`, `GOSSIP=10`, `FORWARDED_REQUEST=11`.
- `Message.new_request()` gains keyword-only `msg_type: MessageType = MessageType.REQUEST`, preserving all existing callers while allowing control/forwarded messages.
- `encode_task_request(task_name, payload, *, routing_key="") -> bytes`.
- `decode_task_request(data) -> TaskRequestData` where `TaskRequestData` has `task_name`, `payload`, `routing_key`.
- `cluster.codec` produces `AckData`, `ForwardedTaskData`, member conversion, and encode/decode functions for join, ping, ACK, ping-request, gossip, and forwarded tasks.

- [ ] **Step 1: Write failing protocol/message tests**

Extend `tests/unit/test_message.py`:

```python
from distsys.protocol.message import Message, MessageType


def test_phase3_message_type_numbers_preserve_protocol_compatibility():
    assert MessageType.REQUEST == 1
    assert MessageType.RESPONSE == 2
    assert MessageType.ERROR == 3
    assert MessageType.HEARTBEAT == 4
    assert MessageType.JOIN_REQUEST == 5
    assert MessageType.JOIN_RESPONSE == 6
    assert MessageType.PING == 7
    assert MessageType.ACK == 8
    assert MessageType.PING_REQ == 9
    assert MessageType.GOSSIP == 10
    assert MessageType.FORWARDED_REQUEST == 11


def test_new_request_accepts_explicit_message_type():
    message = Message.new_request(
        sender_id="node-0",
        payload=b"control",
        msg_type=MessageType.PING,
    )
    assert message.msg_type is MessageType.PING
```

Extend `tests/unit/test_codec.py`:

```python
from distsys.protocol.codec import decode_task_request, encode_task_request


def test_task_request_round_trip_preserves_optional_routing_key():
    encoded = encode_task_request(
        "echo",
        {"message": "hello"},
        routing_key="customer-123",
    )
    decoded = decode_task_request(encoded)
    assert decoded.task_name == "echo"
    assert decoded.payload == {"message": "hello"}
    assert decoded.routing_key == "customer-123"


def test_task_request_without_routing_key_remains_backward_compatible():
    encoded = encode_task_request("echo", {"message": "hello"})
    decoded = decode_task_request(encoded)
    assert decoded.routing_key == ""
```

Create `tests/unit/test_cluster_codec.py`:

```python
from distsys.cluster.codec import (
    decode_ack,
    decode_forwarded_request,
    decode_gossip,
    decode_join_request,
    decode_join_response,
    decode_ping,
    decode_ping_request,
    encode_ack,
    encode_forwarded_request,
    encode_gossip,
    encode_join_request,
    encode_join_response,
    encode_ping,
    encode_ping_request,
)
from distsys.cluster.member import ClusterMember, MemberStatus


def member(node_id: str, port: int, incarnation: int = 10) -> ClusterMember:
    return ClusterMember(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        status=MemberStatus.ALIVE,
        incarnation=incarnation,
    )


def test_join_round_trip():
    local = member("node-1", 18001)
    assert decode_join_request(encode_join_request(local)) == local
    snapshot = (member("node-0", 18000), local)
    assert decode_join_response(encode_join_response(snapshot)) == snapshot


def test_ping_ack_and_ping_request_round_trip():
    snapshot = (member("node-0", 18000), member("node-1", 18001))
    assert decode_ping(encode_ping(snapshot)) == snapshot

    ack = decode_ack(
        encode_ack(success=True, target_node_id="node-1", gossip=snapshot)
    )
    assert ack.success is True
    assert ack.target_node_id == "node-1"
    assert ack.gossip == snapshot

    target, gossip = decode_ping_request(
        encode_ping_request(target=member("node-1", 18001), gossip=snapshot)
    )
    assert target == member("node-1", 18001)
    assert gossip == snapshot


def test_gossip_round_trip():
    snapshot = (member("node-0", 18000), member("node-1", 18001))
    assert decode_gossip(encode_gossip(snapshot)) == snapshot


def test_forwarded_task_round_trip():
    encoded = encode_forwarded_request(
        task_name="echo",
        payload={"message": "forwarded"},
        routing_key="customer-123",
        origin_node_id="node-0",
        remaining_timeout_ms=900,
    )
    decoded = decode_forwarded_request(encoded)
    assert decoded.task.task_name == "echo"
    assert decoded.task.payload == {"message": "forwarded"}
    assert decoded.task.routing_key == "customer-123"
    assert decoded.origin_node_id == "node-0"
    assert decoded.remaining_timeout_ms == 900
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q \
  tests/unit/test_message.py \
  tests/unit/test_codec.py \
  tests/unit/test_cluster_codec.py
```

Expected: failures for missing Phase-3 enum values/schema/messages/codecs.

- [ ] **Step 3: Extend `proto/messages.proto` without renumbering existing fields**

Append the new error/status/messages and add `routing_key = 3` to `TaskRequest`:

```proto
enum ErrorCode {
  ERROR_CODE_UNSPECIFIED = 0;
  UNKNOWN_TASK = 1;
  INVALID_REQUEST = 2;
  INTERNAL_ERROR = 3;
  TIMEOUT = 4;
  OVERLOADED = 5;
  RATE_LIMITED = 6;
  NO_ROUTE = 7;
  PEER_UNAVAILABLE = 8;
}

enum MemberStatus {
  MEMBER_STATUS_UNSPECIFIED = 0;
  ALIVE = 1;
  SUSPECT = 2;
  DEAD = 3;
}

message TaskRequest {
  string task_name = 1;
  bytes payload_json = 2;
  string routing_key = 3;
}

message ClusterMember {
  string node_id = 1;
  string host = 2;
  uint32 port = 3;
  MemberStatus status = 4;
  uint64 incarnation = 5;
}

message JoinRequest {
  ClusterMember member = 1;
}

message JoinResponse {
  repeated ClusterMember members = 1;
}

message Ping {
  repeated ClusterMember gossip = 1;
}

message Ack {
  bool success = 1;
  string target_node_id = 2;
  repeated ClusterMember gossip = 3;
}

message PingRequest {
  ClusterMember target = 1;
  repeated ClusterMember gossip = 2;
}

message Gossip {
  repeated ClusterMember members = 1;
}

message ForwardedTaskRequest {
  TaskRequest request = 1;
  string origin_node_id = 2;
  uint32 remaining_timeout_ms = 3;
}
```

Run generation immediately after editing the schema:

```bash
make proto
```

- [ ] **Step 4: Extend `MessageType` and request construction**

Modify `src/distsys/protocol/message.py` so the enum and request factory are:

```python
class MessageType(IntEnum):
    REQUEST = 1
    RESPONSE = 2
    ERROR = 3
    HEARTBEAT = 4
    JOIN_REQUEST = 5
    JOIN_RESPONSE = 6
    PING = 7
    ACK = 8
    PING_REQ = 9
    GOSSIP = 10
    FORWARDED_REQUEST = 11
```

```python
@classmethod
def new_request(
    cls,
    *,
    sender_id: str,
    payload: bytes,
    correlation_id: str | None = None,
    ttl: int = 8,
    msg_type: MessageType = MessageType.REQUEST,
) -> Message:
    return cls(
        msg_type=msg_type,
        sender_id=sender_id,
        correlation_id=correlation_id or str(uuid.uuid4()),
        timestamp_ms=int(time.time() * 1000),
        ttl=ttl,
        payload=payload,
    )
```

- [ ] **Step 5: Change task request codec to a typed result**

In `src/distsys/protocol/codec.py`, add:

```python
@dataclass(slots=True, frozen=True)
class TaskRequestData:
    task_name: str
    payload: Any
    routing_key: str
```

Replace task request encode/decode signatures with:

```python
def encode_task_request(task_name: str, payload: Any, *, routing_key: str = "") -> bytes:
    if not task_name:
        raise DecodeError("task_name is required")
    request = messages_pb2.TaskRequest(
        task_name=task_name,
        payload_json=_json_dump(payload),
        routing_key=routing_key,
    )
    return request.SerializeToString()


def decode_task_request(data: bytes) -> TaskRequestData:
    request = messages_pb2.TaskRequest()
    try:
        request.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError("invalid TaskRequest protobuf") from exc
    if not request.task_name:
        raise DecodeError("task_name is required")
    return TaskRequestData(
        task_name=request.task_name,
        payload=_json_load(request.payload_json),
        routing_key=request.routing_key,
    )
```

Any existing test/caller unpacking `decode_task_request()` as a tuple must be updated to use `.task_name`, `.payload`, and `.routing_key` in Task 13 when node integration changes. Unit codec tests are changed now.

- [ ] **Step 6: Implement cluster codecs**

Create `src/distsys/cluster/codec.py` with these public dataclasses and functions:

```python
from __future__ import annotations

from dataclasses import dataclass

from google.protobuf.message import DecodeError as ProtobufDecodeError

from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.proto import messages_pb2
from distsys.protocol.codec import TaskRequestData, decode_task_request, encode_task_request
from distsys.protocol.errors import DecodeError


@dataclass(slots=True, frozen=True)
class AckData:
    success: bool
    target_node_id: str
    gossip: tuple[ClusterMember, ...]


@dataclass(slots=True, frozen=True)
class ForwardedTaskData:
    task: TaskRequestData
    origin_node_id: str
    remaining_timeout_ms: int


def member_to_proto(member: ClusterMember) -> messages_pb2.ClusterMember:
    return messages_pb2.ClusterMember(
        node_id=member.node_id,
        host=member.host,
        port=member.port,
        status=int(member.status),
        incarnation=member.incarnation,
    )


def member_from_proto(value: messages_pb2.ClusterMember) -> ClusterMember:
    if not value.node_id or not value.host:
        raise DecodeError("cluster member node_id and host are required")
    try:
        status = MemberStatus(value.status)
    except ValueError as exc:
        raise DecodeError(f"invalid cluster member status: {value.status}") from exc
    try:
        return ClusterMember(
            node_id=value.node_id,
            host=value.host,
            port=value.port,
            status=status,
            incarnation=value.incarnation,
        )
    except ValueError as exc:
        raise DecodeError(str(exc)) from exc


def _parse(message, data: bytes, label: str):
    try:
        message.ParseFromString(data)
    except ProtobufDecodeError as exc:
        raise DecodeError(f"invalid {label} protobuf") from exc
    return message
```

Then implement the public codec surface exactly as follows:

```python
def encode_join_request(member: ClusterMember) -> bytes:
    return messages_pb2.JoinRequest(member=member_to_proto(member)).SerializeToString()


def decode_join_request(data: bytes) -> ClusterMember:
    value = _parse(messages_pb2.JoinRequest(), data, "JoinRequest")
    return member_from_proto(value.member)


def encode_join_response(members: tuple[ClusterMember, ...]) -> bytes:
    value = messages_pb2.JoinResponse()
    value.members.extend(member_to_proto(member) for member in members)
    return value.SerializeToString()


def decode_join_response(data: bytes) -> tuple[ClusterMember, ...]:
    value = _parse(messages_pb2.JoinResponse(), data, "JoinResponse")
    return tuple(member_from_proto(member) for member in value.members)


def encode_ping(gossip: tuple[ClusterMember, ...]) -> bytes:
    value = messages_pb2.Ping()
    value.gossip.extend(member_to_proto(member) for member in gossip)
    return value.SerializeToString()


def decode_ping(data: bytes) -> tuple[ClusterMember, ...]:
    value = _parse(messages_pb2.Ping(), data, "Ping")
    return tuple(member_from_proto(member) for member in value.gossip)


def encode_ack(
    *,
    success: bool,
    target_node_id: str,
    gossip: tuple[ClusterMember, ...],
) -> bytes:
    value = messages_pb2.Ack(success=success, target_node_id=target_node_id)
    value.gossip.extend(member_to_proto(member) for member in gossip)
    return value.SerializeToString()


def decode_ack(data: bytes) -> AckData:
    value = _parse(messages_pb2.Ack(), data, "Ack")
    return AckData(
        success=value.success,
        target_node_id=value.target_node_id,
        gossip=tuple(member_from_proto(member) for member in value.gossip),
    )


def encode_ping_request(
    *,
    target: ClusterMember,
    gossip: tuple[ClusterMember, ...],
) -> bytes:
    value = messages_pb2.PingRequest(target=member_to_proto(target))
    value.gossip.extend(member_to_proto(member) for member in gossip)
    return value.SerializeToString()


def decode_ping_request(
    data: bytes,
) -> tuple[ClusterMember, tuple[ClusterMember, ...]]:
    value = _parse(messages_pb2.PingRequest(), data, "PingRequest")
    return (
        member_from_proto(value.target),
        tuple(member_from_proto(member) for member in value.gossip),
    )


def encode_gossip(members: tuple[ClusterMember, ...]) -> bytes:
    value = messages_pb2.Gossip()
    value.members.extend(member_to_proto(member) for member in members)
    return value.SerializeToString()


def decode_gossip(data: bytes) -> tuple[ClusterMember, ...]:
    value = _parse(messages_pb2.Gossip(), data, "Gossip")
    return tuple(member_from_proto(member) for member in value.members)


def encode_forwarded_request(
    *,
    task_name: str,
    payload: object,
    routing_key: str,
    origin_node_id: str,
    remaining_timeout_ms: int,
) -> bytes:
    if not origin_node_id:
        raise DecodeError("origin_node_id is required")
    task = messages_pb2.TaskRequest()
    task.ParseFromString(
        encode_task_request(task_name, payload, routing_key=routing_key)
    )
    return messages_pb2.ForwardedTaskRequest(
        request=task,
        origin_node_id=origin_node_id,
        remaining_timeout_ms=remaining_timeout_ms,
    ).SerializeToString()


def decode_forwarded_request(data: bytes) -> ForwardedTaskData:
    value = _parse(
        messages_pb2.ForwardedTaskRequest(), data, "ForwardedTaskRequest"
    )
    if not value.origin_node_id:
        raise DecodeError("origin_node_id is required")
    return ForwardedTaskData(
        task=decode_task_request(value.request.SerializeToString()),
        origin_node_id=value.origin_node_id,
        remaining_timeout_ms=value.remaining_timeout_ms,
    )
```

The bodies must construct/parse the exact generated Protobuf messages. `encode_forwarded_request()` builds a `TaskRequest` by parsing the bytes returned from `encode_task_request()` into `messages_pb2.TaskRequest`, then embeds it. `decode_forwarded_request()` serializes the nested `request` back through `decode_task_request()` so JSON validation remains centralized. It must reject an empty `origin_node_id` with `DecodeError("origin_node_id is required")`.

- [ ] **Step 7: Verify GREEN**

```bash
make proto
python -m pytest -q \
  tests/unit/test_message.py \
  tests/unit/test_codec.py \
  tests/unit/test_cluster_codec.py \
  tests/unit/test_framing.py
python -m ruff check src/distsys/protocol src/distsys/cluster tests/unit/test_cluster_codec.py
python -m mypy src/distsys/protocol src/distsys/cluster
```

Expected: all pass; existing framing tests prove new message types still use protocol version 1.

- [ ] **Step 8: Commit**

```bash
git add \
  proto/messages.proto \
  src/distsys/proto/messages_pb2.py \
  src/distsys/proto/messages_pb2.pyi \
  src/distsys/protocol/message.py \
  src/distsys/protocol/codec.py \
  src/distsys/cluster/codec.py \
  tests/unit/test_message.py \
  tests/unit/test_codec.py \
  tests/unit/test_cluster_codec.py

git commit -m "feat: extend protocol for cluster control and routing"
```

---
### Task 4: Deterministic Consistent Hash Ring

**Files:**
- Create: `src/distsys/cluster/consistent_hash.py`
- Create: `tests/unit/test_consistent_hash.py`

**Interfaces:**
- Consumes: `ClusterMember`, `MemberStatus`.
- Produces: `NoRouteError`.
- Produces: `ConsistentHashRing(virtual_nodes: int = 64)`.
- Produces: `rebuild(members)`, `owner(key)`, and `candidates(key)`.

- [ ] **Step 1: Write failing ring tests**

Create `tests/unit/test_consistent_hash.py`:

```python
import pytest

from distsys.cluster.consistent_hash import ConsistentHashRing, NoRouteError
from distsys.cluster.member import ClusterMember, MemberStatus


def member(node_id: str, port: int, status: MemberStatus = MemberStatus.ALIVE):
    return ClusterMember(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        status=status,
        incarnation=1,
    )


def test_identical_membership_builds_identical_ownership():
    members = [member("node-0", 18000), member("node-1", 18001), member("node-2", 18002)]
    left = ConsistentHashRing(virtual_nodes=64)
    right = ConsistentHashRing(virtual_nodes=64)
    left.rebuild(members)
    right.rebuild(reversed(members))
    assert [left.owner(f"key-{i}").node_id for i in range(100)] == [
        right.owner(f"key-{i}").node_id for i in range(100)
    ]


def test_only_alive_members_participate():
    ring = ConsistentHashRing(virtual_nodes=64)
    ring.rebuild(
        [
            member("node-0", 18000),
            member("node-1", 18001, MemberStatus.SUSPECT),
            member("node-2", 18002, MemberStatus.DEAD),
        ]
    )
    assert {ring.owner(f"key-{i}").node_id for i in range(20)} == {"node-0"}


def test_candidates_are_unique_physical_members():
    ring = ConsistentHashRing(virtual_nodes=64)
    ring.rebuild([member("node-0", 18000), member("node-1", 18001), member("node-2", 18002)])
    candidates = ring.candidates("customer-123")
    assert len(candidates) == 3
    assert len({candidate.node_id for candidate in candidates}) == 3
    assert candidates[0] == ring.owner("customer-123")


def test_removing_member_only_moves_keys_owned_by_that_member():
    members = [member("node-0", 18000), member("node-1", 18001), member("node-2", 18002)]
    before = ConsistentHashRing(virtual_nodes=64)
    before.rebuild(members)
    previous = {f"key-{i}": before.owner(f"key-{i}").node_id for i in range(500)}

    after = ConsistentHashRing(virtual_nodes=64)
    after.rebuild([members[0], members[1]])
    for key, old_owner in previous.items():
        new_owner = after.owner(key).node_id
        if old_owner != "node-2":
            assert new_owner == old_owner


def test_empty_ring_raises_no_route():
    ring = ConsistentHashRing()
    with pytest.raises(NoRouteError):
        ring.owner("customer-123")
    with pytest.raises(NoRouteError):
        ring.candidates("customer-123")
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/unit/test_consistent_hash.py
```

Expected: import failure for missing ring module.

- [ ] **Step 3: Implement the ring**

Create `src/distsys/cluster/consistent_hash.py`:

```python
"""Deterministic SHA-256 consistent hash ring."""

from __future__ import annotations

import bisect
import hashlib
from collections.abc import Iterable

from distsys.cluster.member import ClusterMember, MemberStatus


class NoRouteError(LookupError):
    pass


def _hash(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest(), "big")


class ConsistentHashRing:
    def __init__(self, *, virtual_nodes: int = 64) -> None:
        if virtual_nodes < 1:
            raise ValueError("virtual_nodes must be at least 1")
        self.virtual_nodes = virtual_nodes
        self._positions: list[int] = []
        self._owners: list[ClusterMember] = []

    def rebuild(self, members: Iterable[ClusterMember]) -> None:
        points: list[tuple[int, ClusterMember]] = []
        for member in members:
            if member.status is not MemberStatus.ALIVE:
                continue
            for index in range(self.virtual_nodes):
                points.append((_hash(f"{member.node_id}#{index}"), member))
        points.sort(key=lambda item: (item[0], item[1].node_id))
        self._positions = [position for position, _ in points]
        self._owners = [member for _, member in points]

    def candidates(self, key: str) -> list[ClusterMember]:
        if not self._positions:
            raise NoRouteError("no ALIVE cluster members are available")
        start = bisect.bisect_left(self._positions, _hash(key))
        result: list[ClusterMember] = []
        seen: set[str] = set()
        for offset in range(len(self._owners)):
            member = self._owners[(start + offset) % len(self._owners)]
            if member.node_id in seen:
                continue
            seen.add(member.node_id)
            result.append(member)
        return result

    def owner(self, key: str) -> ClusterMember:
        return self.candidates(key)[0]
```

- [ ] **Step 4: Verify GREEN**

```bash
python -m pytest -q tests/unit/test_consistent_hash.py
python -m ruff check src/distsys/cluster/consistent_hash.py tests/unit/test_consistent_hash.py
python -m mypy src/distsys/cluster/consistent_hash.py
```

- [ ] **Step 5: Commit**

```bash
git add src/distsys/cluster/consistent_hash.py tests/unit/test_consistent_hash.py
git commit -m "feat: add deterministic consistent hash ring"
```

---

### Task 5: Cluster Configuration and Validation

**Files:**
- Modify: `src/distsys/utils/config.py`
- Modify: `.env.example`
- Create: `tests/unit/test_cluster_config.py`

**Interfaces:**
- Consumes: `SeedAddress.parse()`.
- Extends `Settings` with cluster fields from the approved spec.
- Produces: `cluster_seeds: tuple[SeedAddress, ...]` rather than raw strings.

- [ ] **Step 1: Write failing configuration tests**

Create `tests/unit/test_cluster_config.py`:

```python
import pytest

from distsys.cluster.member import SeedAddress
from distsys.utils.config import Settings


def test_cluster_defaults_keep_phase2_standalone_behavior():
    settings = Settings()
    assert settings.cluster_enabled is False
    assert settings.cluster_seeds == ()
    assert settings.cluster_virtual_nodes == 64
    assert settings.cluster_probe_interval_seconds == 1.0
    assert settings.cluster_ping_timeout_seconds == 0.25
    assert settings.cluster_indirect_timeout_seconds == 0.50
    assert settings.cluster_indirect_probe_count == 2
    assert settings.cluster_suspicion_timeout_seconds == 3.0
    assert settings.cluster_dead_retention_seconds == 30.0
    assert settings.cluster_gossip_interval_seconds == 1.0


def test_cluster_env_parses_seed_list(monkeypatch):
    monkeypatch.setenv("CLUSTER_ENABLED", "true")
    monkeypatch.setenv("CLUSTER_SEEDS", "127.0.0.1:18000, 127.0.0.1:18001")
    settings = Settings.from_env()
    assert settings.cluster_enabled is True
    assert settings.cluster_seeds == (
        SeedAddress("127.0.0.1", 18000),
        SeedAddress("127.0.0.1", 18001),
    )


def test_dead_retention_must_exceed_suspicion_timeout():
    with pytest.raises(ValueError, match="dead retention"):
        Settings(
            cluster_suspicion_timeout_seconds=3.0,
            cluster_dead_retention_seconds=3.0,
        )


def test_virtual_nodes_must_be_positive():
    with pytest.raises(ValueError, match="virtual nodes"):
        Settings(cluster_virtual_nodes=0)
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/unit/test_cluster_config.py
```

- [ ] **Step 3: Extend `Settings`**

Add these fields to `Settings`:

```python
cluster_enabled: bool = False
cluster_seeds: tuple[SeedAddress, ...] = ()
cluster_virtual_nodes: int = 64
cluster_probe_interval_seconds: float = 1.0
cluster_ping_timeout_seconds: float = 0.25
cluster_indirect_timeout_seconds: float = 0.50
cluster_indirect_probe_count: int = 2
cluster_suspicion_timeout_seconds: float = 3.0
cluster_dead_retention_seconds: float = 30.0
cluster_gossip_interval_seconds: float = 1.0
```

Add helper functions above the dataclass:

```python
def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _env_seeds() -> tuple[SeedAddress, ...]:
    raw = os.getenv("CLUSTER_SEEDS", "").strip()
    if not raw:
        return ()
    return tuple(SeedAddress.parse(item.strip()) for item in raw.split(",") if item.strip())
```

Add validation in `__post_init__`:

```python
if self.cluster_virtual_nodes < 1:
    raise ValueError("cluster virtual nodes must be at least 1")
if self.cluster_probe_interval_seconds <= 0:
    raise ValueError("cluster probe interval must be greater than zero")
if self.cluster_ping_timeout_seconds <= 0:
    raise ValueError("cluster ping timeout must be greater than zero")
if self.cluster_indirect_timeout_seconds <= 0:
    raise ValueError("cluster indirect timeout must be greater than zero")
if self.cluster_indirect_probe_count < 0:
    raise ValueError("cluster indirect probe count cannot be negative")
if self.cluster_suspicion_timeout_seconds <= 0:
    raise ValueError("cluster suspicion timeout must be greater than zero")
if self.cluster_dead_retention_seconds <= self.cluster_suspicion_timeout_seconds:
    raise ValueError("cluster dead retention must exceed suspicion timeout")
if self.cluster_gossip_interval_seconds <= 0:
    raise ValueError("cluster gossip interval must be greater than zero")
```

Populate the fields in `from_env()` with the exact environment variable names in the spec.

- [ ] **Step 4: Update `.env.example`**

Append:

```dotenv
CLUSTER_ENABLED=false
CLUSTER_SEEDS=
CLUSTER_VIRTUAL_NODES=64
CLUSTER_PROBE_INTERVAL_SECONDS=1.0
CLUSTER_PING_TIMEOUT_SECONDS=0.25
CLUSTER_INDIRECT_TIMEOUT_SECONDS=0.50
CLUSTER_INDIRECT_PROBE_COUNT=2
CLUSTER_SUSPICION_TIMEOUT_SECONDS=3.0
CLUSTER_DEAD_RETENTION_SECONDS=30.0
CLUSTER_GOSSIP_INTERVAL_SECONDS=1.0
```

- [ ] **Step 5: Verify GREEN and Phase-2 configuration regression**

```bash
python -m pytest -q tests/unit/test_config.py tests/unit/test_cluster_config.py
python -m ruff check src/distsys/utils/config.py tests/unit/test_cluster_config.py
python -m mypy src/distsys/utils/config.py
```

- [ ] **Step 6: Commit**

```bash
git add src/distsys/utils/config.py .env.example tests/unit/test_cluster_config.py
git commit -m "feat: add cluster runtime configuration"
```

---

### Task 6: Diagnostic `cluster.whoami` Task

**Files:**
- Modify: `src/distsys/compute/tasks.py`
- Modify: `src/distsys/compute/classification.py`
- Modify: `tests/unit/test_compute_tasks.py`
- Modify: `tests/unit/test_classification.py`

**Interfaces:**
- Produces: `make_whoami_task(node_id: str) -> Callable[[Any], Awaitable[dict[str, str]]]`.
- Registers `cluster.whoami` as `ExecutionClass.ASYNC` in the default classifier.
- `DistributedNode` will register the task on its default router in Task 13.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_compute_tasks.py`:

```python
import pytest

from distsys.compute.tasks import make_whoami_task


@pytest.mark.asyncio
async def test_whoami_task_reports_bound_node_identity():
    task = make_whoami_task("node-2")
    assert await task({}) == {"node_id": "node-2"}
```

Append to `tests/unit/test_classification.py`:

```python
from distsys.compute.classification import ExecutionClass, TaskClassifier


def test_cluster_whoami_is_async():
    assert TaskClassifier.default().classify("cluster.whoami") is ExecutionClass.ASYNC
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/unit/test_compute_tasks.py tests/unit/test_classification.py
```

- [ ] **Step 3: Implement the task factory and classification**

Add to `src/distsys/compute/tasks.py`:

```python
def make_whoami_task(node_id: str):
    if not node_id:
        raise ValueError("node_id is required")

    async def whoami_task(payload: Any) -> dict[str, str]:
        _require_mapping(payload)
        return {"node_id": node_id}

    return whoami_task
```

Add to `TaskClassifier.default()`:

```python
classifier.register("cluster.whoami", ExecutionClass.ASYNC)
```

- [ ] **Step 4: Verify GREEN**

```bash
python -m pytest -q tests/unit/test_compute_tasks.py tests/unit/test_classification.py
python -m ruff check src/distsys/compute tests/unit/test_compute_tasks.py tests/unit/test_classification.py
python -m mypy src/distsys/compute
```

- [ ] **Step 5: Commit**

```bash
git add \
  src/distsys/compute/tasks.py \
  src/distsys/compute/classification.py \
  tests/unit/test_compute_tasks.py \
  tests/unit/test_classification.py

git commit -m "feat: add cluster routing diagnostic task"
```

---
### Task 7: Peer Networking, Transport Retry, and Per-Peer Circuit Breakers

**Files:**
- Create: `src/distsys/cluster/peer_client.py`
- Create: `tests/unit/test_peer_client.py`

**Interfaces:**
- Consumes: cluster codecs, `ClusterMember`, `SeedAddress`, framed TCP protocol, `RetryPolicy`, `retry_async`, `CircuitBreaker`, `CircuitOpenError`, and `Deadline`.
- Produces exceptions:
  - `PeerTransportError(ConnectionError)` for exhausted transport/protocol failures.
  - `PeerProtocolError(ConnectionError)` for correlation/type violations; this is retryable transport/protocol failure.
  - `PeerApplicationError(RuntimeError)` with `.code` and `.message` for structured remote task errors.
- Produces control operations that do **not** use task retry/breakers:
  - `join(seed, local_member, timeout_seconds)`
  - `ping(peer, gossip, timeout_seconds)`
  - `ping_request(helper, target, gossip, timeout_seconds)`
  - `gossip(peer, members, timeout_seconds)`
- Produces `forward_task(peer, task_name, payload, routing_key, origin_node_id, deadline)` using retry + per-peer breaker.

- [ ] **Step 1: Write failing peer-client tests around behavior, not socket internals**

Create `tests/unit/test_peer_client.py`. Use a small fake subclass that overrides `_exchange_endpoint()` so tests exercise retry/breaker/application-decoding logic without real sockets:

```python
import asyncio

import pytest

from distsys.cluster.codec import encode_ack
from distsys.cluster.member import ClusterMember, MemberStatus, SeedAddress
from distsys.cluster.peer_client import (
    PeerApplicationError,
    PeerClient,
    PeerProtocolError,
    PeerTransportError,
)
from distsys.proto import messages_pb2
from distsys.protocol.codec import encode_task_response
from distsys.protocol.message import Message, MessageType
from distsys.resilience.circuit_breaker import CircuitOpenError
from distsys.resilience.deadline import Deadline
from distsys.resilience.retry import RetryPolicy


def member(node_id: str = "node-1", port: int = 18001) -> ClusterMember:
    return ClusterMember(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        status=MemberStatus.ALIVE,
        incarnation=1,
    )


class ScriptedPeerClient(PeerClient):
    def __init__(self, script):
        super().__init__(
            local_node_id="node-0",
            retry_policy=RetryPolicy(
                max_attempts=3,
                base_delay_seconds=0.0,
                max_delay_seconds=0.0,
            ),
            circuit_breaker_failure_threshold=2,
            circuit_breaker_recovery_seconds=60.0,
        )
        self.script = list(script)
        self.calls = 0

    async def _exchange_endpoint(self, host, port, message, *, timeout_seconds):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return item(message)
        return item


def success_response(request: Message) -> Message:
    return Message.new_response(
        sender_id="node-1",
        correlation_id=request.correlation_id,
        payload=encode_task_response(success=True, result={"ok": True}),
    )


def invalid_response(request: Message) -> Message:
    return Message.new_response(
        sender_id="node-1",
        correlation_id=request.correlation_id,
        payload=encode_task_response(
            success=False,
            error_code=messages_pb2.INVALID_REQUEST,
            error_message="bad payload",
        ),
        msg_type=MessageType.ERROR,
    )


@pytest.mark.asyncio
async def test_forward_task_retries_transport_failure_then_succeeds():
    client = ScriptedPeerClient([ConnectionRefusedError(), success_response])
    result = await client.forward_task(
        member(),
        task_name="echo",
        payload={"message": "hello"},
        routing_key="customer-123",
        origin_node_id="node-0",
        deadline=Deadline.after(1.0),
    )
    assert result == {"ok": True}
    assert client.calls == 2


@pytest.mark.asyncio
async def test_structured_application_error_is_not_retried_or_counted_as_transport_failure():
    client = ScriptedPeerClient([invalid_response])
    with pytest.raises(PeerApplicationError) as exc:
        await client.forward_task(
            member(),
            task_name="echo",
            payload={},
            routing_key="key",
            origin_node_id="node-0",
            deadline=Deadline.after(1.0),
        )
    assert exc.value.code == messages_pb2.INVALID_REQUEST
    assert client.calls == 1
    assert client.breaker_for("node-1").failure_count == 0


@pytest.mark.asyncio
async def test_exhausted_transport_failures_raise_peer_transport_error():
    client = ScriptedPeerClient(
        [ConnectionRefusedError(), ConnectionResetError(), TimeoutError()]
    )
    with pytest.raises(PeerTransportError):
        await client.forward_task(
            member(),
            task_name="echo",
            payload={},
            routing_key="key",
            origin_node_id="node-0",
            deadline=Deadline.after(1.0),
        )


@pytest.mark.asyncio
async def test_open_circuit_skips_new_transport_call():
    client = ScriptedPeerClient([ConnectionRefusedError(), ConnectionRefusedError()])
    with pytest.raises((PeerTransportError, CircuitOpenError)):
        await client.forward_task(
            member(),
            task_name="echo",
            payload={},
            routing_key="key",
            origin_node_id="node-0",
            deadline=Deadline.after(1.0),
        )
    calls_after_open = client.calls
    with pytest.raises(CircuitOpenError):
        await client.forward_task(
            member(),
            task_name="echo",
            payload={},
            routing_key="key",
            origin_node_id="node-0",
            deadline=Deadline.after(1.0),
        )
    assert client.calls == calls_after_open


@pytest.mark.asyncio
async def test_control_ping_does_not_use_task_retry():
    client = ScriptedPeerClient([ConnectionRefusedError()])
    with pytest.raises(ConnectionRefusedError):
        await client.ping(member(), (), timeout_seconds=0.1)
    assert client.calls == 1
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/unit/test_peer_client.py
```

Expected: import failure for missing `PeerClient`.

- [ ] **Step 3: Implement peer-client transport primitives**

Create `src/distsys/cluster/peer_client.py` with this public shape:

```python
"""One-shot peer RPC plus task retry/circuit-breaker boundaries."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from distsys.cluster.codec import (
    AckData,
    decode_ack,
    decode_join_response,
    encode_forwarded_request,
    encode_gossip,
    encode_join_request,
    encode_ping,
    encode_ping_request,
)
from distsys.cluster.member import ClusterMember, SeedAddress
from distsys.protocol.codec import decode_task_response
from distsys.protocol.framing import DEFAULT_MAX_FRAME_SIZE, encode_frame, read_message
from distsys.protocol.message import Message, MessageType
from distsys.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError
from distsys.resilience.deadline import Deadline, DeadlineExceeded
from distsys.resilience.retry import RetryPolicy, retry_async


class PeerProtocolError(ConnectionError):
    pass


class PeerTransportError(ConnectionError):
    pass


class PeerApplicationError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_RETRYABLE = (ConnectionError, TimeoutError, OSError, PeerProtocolError)
```

Constructor and breaker lookup:

```python
class PeerClient:
    def __init__(
        self,
        *,
        local_node_id: str,
        retry_policy: RetryPolicy,
        circuit_breaker_failure_threshold: int,
        circuit_breaker_recovery_seconds: float,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
    ) -> None:
        self.local_node_id = local_node_id
        self.retry_policy = retry_policy
        self.circuit_breaker_failure_threshold = circuit_breaker_failure_threshold
        self.circuit_breaker_recovery_seconds = circuit_breaker_recovery_seconds
        self.max_frame_size = max_frame_size
        self._breakers: dict[str, CircuitBreaker] = {}

    def breaker_for(self, node_id: str) -> CircuitBreaker:
        breaker = self._breakers.get(node_id)
        if breaker is None:
            breaker = CircuitBreaker(
                failure_threshold=self.circuit_breaker_failure_threshold,
                recovery_timeout_seconds=self.circuit_breaker_recovery_seconds,
            )
            self._breakers[node_id] = breaker
        return breaker
```

The raw exchange implementation must use one timeout for the whole open/write/read operation:

```python
    async def _exchange_endpoint(
        self,
        host: str,
        port: int,
        message: Message,
        *,
        timeout_seconds: float,
    ) -> Message:
        if timeout_seconds <= 0:
            raise TimeoutError("peer exchange timeout exhausted")
        async with asyncio.timeout(timeout_seconds):
            reader, writer = await asyncio.open_connection(host, port)
            try:
                writer.write(encode_frame(message, max_frame_size=self.max_frame_size))
                await writer.drain()
                response = await read_message(reader, max_frame_size=self.max_frame_size)
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass
        if response.correlation_id != message.correlation_id:
            raise PeerProtocolError(
                f"expected correlation {message.correlation_id}, got {response.correlation_id}"
            )
        return response
```

Control operations build one control message and call `_exchange_endpoint()` exactly once. For example direct ping:

```python
    async def ping(
        self,
        peer: ClusterMember,
        gossip: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData:
        request = Message.new_request(
            sender_id=self.local_node_id,
            payload=encode_ping(gossip),
            msg_type=MessageType.PING,
        )
        response = await self._exchange_endpoint(
            peer.host, peer.port, request, timeout_seconds=timeout_seconds
        )
        if response.msg_type is not MessageType.ACK:
            raise PeerProtocolError(f"expected ACK, got {response.msg_type.name}")
        return decode_ack(response.payload)
```

Add the remaining control methods exactly as follows:

```python
    async def join(
        self,
        seed: SeedAddress,
        local_member: ClusterMember,
        *,
        timeout_seconds: float,
    ) -> tuple[ClusterMember, ...]:
        request = Message.new_request(
            sender_id=self.local_node_id,
            payload=encode_join_request(local_member),
            msg_type=MessageType.JOIN_REQUEST,
        )
        response = await self._exchange_endpoint(
            seed.host, seed.port, request, timeout_seconds=timeout_seconds
        )
        if response.msg_type is not MessageType.JOIN_RESPONSE:
            raise PeerProtocolError(
                f"expected JOIN_RESPONSE, got {response.msg_type.name}"
            )
        return decode_join_response(response.payload)

    async def ping_request(
        self,
        helper: ClusterMember,
        target: ClusterMember,
        gossip: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData:
        request = Message.new_request(
            sender_id=self.local_node_id,
            payload=encode_ping_request(target=target, gossip=gossip),
            msg_type=MessageType.PING_REQ,
        )
        response = await self._exchange_endpoint(
            helper.host, helper.port, request, timeout_seconds=timeout_seconds
        )
        if response.msg_type is not MessageType.ACK:
            raise PeerProtocolError(f"expected ACK, got {response.msg_type.name}")
        return decode_ack(response.payload)

    async def gossip(
        self,
        peer: ClusterMember,
        members: tuple[ClusterMember, ...],
        *,
        timeout_seconds: float,
    ) -> AckData:
        request = Message.new_request(
            sender_id=self.local_node_id,
            payload=encode_gossip(members),
            msg_type=MessageType.GOSSIP,
        )
        response = await self._exchange_endpoint(
            peer.host, peer.port, request, timeout_seconds=timeout_seconds
        )
        if response.msg_type is not MessageType.ACK:
            raise PeerProtocolError(f"expected ACK, got {response.msg_type.name}")
        return decode_ack(response.payload)
```

Task forwarding uses one logical correlation id across retries. Rebuild the payload on each retry attempt only to decrease `remaining_timeout_ms`; this keeps the same logical request/correlation while enforcing the shared budget more accurately:

```python
    async def forward_task(
        self,
        peer: ClusterMember,
        *,
        task_name: str,
        payload: Any,
        routing_key: str,
        origin_node_id: str,
        deadline: Deadline,
    ) -> Any:
        correlation_id = str(uuid.uuid4())
        breaker = self.breaker_for(peer.node_id)

        async def attempt() -> Message:
            remaining = deadline.remaining()
            if remaining <= 0:
                raise DeadlineExceeded("request deadline exceeded before peer forward")
            request = Message.new_request(
                sender_id=self.local_node_id,
                correlation_id=correlation_id,
                msg_type=MessageType.FORWARDED_REQUEST,
                payload=encode_forwarded_request(
                    task_name=task_name,
                    payload=payload,
                    routing_key=routing_key,
                    origin_node_id=origin_node_id,
                    remaining_timeout_ms=max(1, int(remaining * 1000)),
                ),
            )
            return await breaker.call(
                lambda: self._exchange_endpoint(
                    peer.host,
                    peer.port,
                    request,
                    timeout_seconds=deadline.remaining(),
                )
            )

        try:
            response = await retry_async(
                attempt,
                policy=self.retry_policy,
                should_retry=lambda exc: isinstance(exc, _RETRYABLE)
                and not isinstance(exc, CircuitOpenError),
                deadline=deadline,
            )
        except CircuitOpenError:
            raise
        except DeadlineExceeded:
            raise
        except _RETRYABLE as exc:
            raise PeerTransportError(f"peer {peer.node_id} transport failed") from exc

        if response.msg_type not in (MessageType.RESPONSE, MessageType.ERROR):
            raise PeerProtocolError(
                f"expected task RESPONSE/ERROR, got {response.msg_type.name}"
            )
        decoded = decode_task_response(response.payload)
        if not decoded.success:
            raise PeerApplicationError(decoded.error_code, decoded.error_message)
        return decoded.result
```

- [ ] **Step 4: Verify GREEN**

```bash
python -m pytest -q \
  tests/unit/test_retry.py \
  tests/unit/test_circuit_breaker.py \
  tests/unit/test_peer_client.py
python -m ruff check src/distsys/cluster/peer_client.py tests/unit/test_peer_client.py
python -m mypy src/distsys/cluster/peer_client.py
```

- [ ] **Step 5: Commit**

```bash
git add src/distsys/cluster/peer_client.py tests/unit/test_peer_client.py
git commit -m "feat: add resilient peer transport"
```

---

### Task 8: Keyed Cluster Routing and Candidate Failover

**Files:**
- Create: `src/distsys/cluster/cluster_router.py`
- Create: `tests/unit/test_cluster_router.py`

**Interfaces:**
- Consumes: `ConsistentHashRing`, `PeerClient`, `Deadline`, Protobuf error codes.
- Produces:
  - `LocalOverloadedError`
  - `PeerUnavailableError`
  - `ClusterRouter.execute(task_name, payload, routing_key, deadline)`.
- Local execution dependency has exact callable signature `Callable[[str, Any, Deadline], Awaitable[Any]]`.

- [ ] **Step 1: Write failing routing tests with fakes**

Create `tests/unit/test_cluster_router.py`:

```python
from typing import Any

import pytest

from distsys.cluster.cluster_router import (
    ClusterRouter,
    LocalOverloadedError,
    PeerUnavailableError,
)
from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.peer_client import PeerApplicationError, PeerTransportError
from distsys.proto import messages_pb2
from distsys.resilience.deadline import Deadline


def member(node_id: str, port: int) -> ClusterMember:
    return ClusterMember(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        status=MemberStatus.ALIVE,
        incarnation=1,
    )


class FakePeerClient:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    async def forward_task(self, peer, **kwargs):
        self.calls.append(peer.node_id)
        outcome = self.outcomes[peer.node_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_local_owner_executes_locally():
    local = member("node-0", 18000)
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild([local])
    calls: list[str] = []

    async def execute_local(task_name: str, payload: Any, deadline: Deadline):
        calls.append(task_name)
        return {"node_id": "node-0"}

    router = ClusterRouter(
        local_node_id="node-0",
        ring=ring,
        peer_client=FakePeerClient({}),
        execute_local=execute_local,
    )
    assert await router.execute(
        "cluster.whoami", {}, routing_key="key", deadline=Deadline.after(1.0)
    ) == {"node_id": "node-0"}
    assert calls == ["cluster.whoami"]


@pytest.mark.asyncio
async def test_transport_failure_fails_over_to_next_candidate():
    nodes = [member("node-0", 18000), member("node-1", 18001), member("node-2", 18002)]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(nodes)
    key = next(
        f"key-{i}" for i in range(1000) if ring.owner(f"key-{i}").node_id == "node-1"
    )
    peer = FakePeerClient(
        {
            "node-1": PeerTransportError("down"),
            "node-2": {"node_id": "node-2"},
            "node-0": {"node_id": "node-0"},
        }
    )

    async def execute_local(task_name, payload, deadline):
        return {"node_id": "node-0"}

    router = ClusterRouter(
        local_node_id="node-0", ring=ring, peer_client=peer, execute_local=execute_local
    )
    result = await router.execute(
        "cluster.whoami", {}, routing_key=key, deadline=Deadline.after(1.0)
    )
    assert result["node_id"] != "node-1"
    assert peer.calls[0] == "node-1"


@pytest.mark.asyncio
async def test_invalid_request_is_returned_without_failover():
    nodes = [member("node-0", 18000), member("node-1", 18001)]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(nodes)
    key = next(
        f"key-{i}" for i in range(1000) if ring.owner(f"key-{i}").node_id == "node-1"
    )
    peer = FakePeerClient(
        {"node-1": PeerApplicationError(messages_pb2.INVALID_REQUEST, "bad payload")}
    )

    async def execute_local(task_name, payload, deadline):
        return {"node_id": "node-0"}

    router = ClusterRouter(
        local_node_id="node-0", ring=ring, peer_client=peer, execute_local=execute_local
    )
    with pytest.raises(PeerApplicationError) as exc:
        await router.execute("echo", {}, routing_key=key, deadline=Deadline.after(1.0))
    assert exc.value.code == messages_pb2.INVALID_REQUEST
    assert peer.calls == ["node-1"]


@pytest.mark.asyncio
async def test_all_failover_candidates_exhausted_raises_peer_unavailable():
    nodes = [member("node-1", 18001), member("node-2", 18002)]
    ring = ConsistentHashRing(virtual_nodes=8)
    ring.rebuild(nodes)
    peer = FakePeerClient(
        {
            "node-1": PeerTransportError("down"),
            "node-2": PeerApplicationError(messages_pb2.OVERLOADED, "busy"),
        }
    )

    async def execute_local(task_name, payload, deadline):
        raise AssertionError("local node is not in ring")

    router = ClusterRouter(
        local_node_id="node-0", ring=ring, peer_client=peer, execute_local=execute_local
    )
    with pytest.raises(PeerUnavailableError):
        await router.execute("echo", {}, routing_key="key", deadline=Deadline.after(1.0))
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/unit/test_cluster_router.py
```

- [ ] **Step 3: Implement failover policy exactly**

Create `src/distsys/cluster/cluster_router.py`:

```python
"""Keyed task ownership and deterministic candidate failover."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from distsys.cluster.consistent_hash import ConsistentHashRing
from distsys.cluster.peer_client import (
    PeerApplicationError,
    PeerClient,
    PeerTransportError,
)
from distsys.proto import messages_pb2
from distsys.resilience.circuit_breaker import CircuitOpenError
from distsys.resilience.deadline import Deadline, DeadlineExceeded


class LocalOverloadedError(RuntimeError):
    pass


class PeerUnavailableError(ConnectionError):
    pass


class ClusterRouter:
    def __init__(
        self,
        *,
        local_node_id: str,
        ring: ConsistentHashRing,
        peer_client: PeerClient,
        execute_local: Callable[[str, Any, Deadline], Awaitable[Any]],
    ) -> None:
        self.local_node_id = local_node_id
        self.ring = ring
        self.peer_client = peer_client
        self.execute_local = execute_local

    async def execute(
        self,
        task_name: str,
        payload: Any,
        *,
        routing_key: str,
        deadline: Deadline,
    ) -> Any:
        candidates = self.ring.candidates(routing_key)
        saw_retryable_candidate_failure = False

        for candidate in candidates:
            if deadline.expired():
                raise DeadlineExceeded("request deadline exceeded during cluster routing")

            if candidate.node_id == self.local_node_id:
                try:
                    return await self.execute_local(task_name, payload, deadline)
                except LocalOverloadedError:
                    saw_retryable_candidate_failure = True
                    continue

            try:
                return await self.peer_client.forward_task(
                    candidate,
                    task_name=task_name,
                    payload=payload,
                    routing_key=routing_key,
                    origin_node_id=self.local_node_id,
                    deadline=deadline,
                )
            except (PeerTransportError, CircuitOpenError):
                saw_retryable_candidate_failure = True
                continue
            except PeerApplicationError as exc:
                if exc.code in (messages_pb2.OVERLOADED, messages_pb2.RATE_LIMITED):
                    saw_retryable_candidate_failure = True
                    continue
                raise

        if saw_retryable_candidate_failure:
            raise PeerUnavailableError("all cluster routing candidates are unavailable")
        raise PeerUnavailableError("no usable cluster routing candidate")
```

`NoRouteError` from `ring.candidates()` is intentionally not caught here; the node maps it to `NO_ROUTE`.

- [ ] **Step 4: Verify GREEN**

```bash
python -m pytest -q tests/unit/test_consistent_hash.py tests/unit/test_cluster_router.py
python -m ruff check src/distsys/cluster/cluster_router.py tests/unit/test_cluster_router.py
python -m mypy src/distsys/cluster/cluster_router.py
```

- [ ] **Step 5: Commit**

```bash
git add src/distsys/cluster/cluster_router.py tests/unit/test_cluster_router.py
git commit -m "feat: add consistent-hash cluster routing"
```

---
### Task 9: SWIM-Lite Failure Detector

**Files:**
- Create: `src/distsys/cluster/failure_detector.py`
- Create: `tests/unit/test_failure_detector.py`

**Interfaces:**
- Consumes: `MembershipTable`, `PeerClient`, control ACKs, configurable direct/indirect timings.
- Produces: `FailureDetector.run_once() -> None` for deterministic tests.
- Produces: `FailureDetector.run() -> None` loop for `ClusterService` background execution.
- Constructor accepts `on_membership_change: Callable[[], Awaitable[None]]` and injectable `choice`/`sleep` functions for deterministic tests.

- [ ] **Step 1: Write failing direct/indirect probe tests**

Create `tests/unit/test_failure_detector.py` using a fake membership table with real `MembershipTable` and a scripted peer client:

```python
import pytest

from distsys.cluster.codec import AckData
from distsys.cluster.failure_detector import FailureDetector
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.membership import MembershipTable


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def member(node_id: str, port: int, status: MemberStatus = MemberStatus.ALIVE):
    return ClusterMember(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        status=status,
        incarnation=10,
    )


class FakePeerClient:
    def __init__(self) -> None:
        self.direct = {}
        self.indirect = {}
        self.ping_calls = []
        self.ping_req_calls = []

    async def ping(self, peer, gossip, *, timeout_seconds):
        self.ping_calls.append(peer.node_id)
        outcome = self.direct[peer.node_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def ping_request(self, helper, target, gossip, *, timeout_seconds):
        self.ping_req_calls.append((helper.node_id, target.node_id))
        outcome = self.indirect[(helper.node_id, target.node_id)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_direct_probe_success_keeps_target_alive():
    clock = FakeClock()
    local = member("node-0", 18000)
    target = member("node-1", 18001)
    table = MembershipTable(
        local,
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([target])
    peer = FakePeerClient()
    peer.direct["node-1"] = AckData(True, "node-1", (target,))
    detector = FailureDetector(
        table=table,
        peer_client=peer,
        local_node_id="node-0",
        probe_interval_seconds=1.0,
        ping_timeout_seconds=0.25,
        indirect_timeout_seconds=0.5,
        indirect_probe_count=2,
        on_membership_change=lambda: _noop(),
        choose=lambda items: items[0],
    )
    await detector.run_once()
    assert (await table.get("node-1")).status is MemberStatus.ALIVE  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_indirect_probe_success_avoids_suspicion():
    clock = FakeClock()
    local = member("node-0", 18000)
    target = member("node-1", 18001)
    helper = member("node-2", 18002)
    table = MembershipTable(
        local,
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([target, helper])
    peer = FakePeerClient()
    peer.direct["node-1"] = ConnectionRefusedError()
    peer.indirect[("node-2", "node-1")] = AckData(True, "node-1", (target, helper))
    detector = FailureDetector(
        table=table,
        peer_client=peer,
        local_node_id="node-0",
        probe_interval_seconds=1.0,
        ping_timeout_seconds=0.25,
        indirect_timeout_seconds=0.5,
        indirect_probe_count=2,
        on_membership_change=lambda: _noop(),
        choose=lambda items: next(item for item in items if item.node_id == "node-1"),
    )
    await detector.run_once()
    assert (await table.get("node-1")).status is MemberStatus.ALIVE  # type: ignore[union-attr]
    assert peer.ping_req_calls == [("node-2", "node-1")]


@pytest.mark.asyncio
async def test_failed_direct_and_indirect_probe_marks_suspect():
    clock = FakeClock()
    local = member("node-0", 18000)
    target = member("node-1", 18001)
    helper = member("node-2", 18002)
    table = MembershipTable(
        local,
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([target, helper])
    peer = FakePeerClient()
    peer.direct["node-1"] = TimeoutError()
    peer.indirect[("node-2", "node-1")] = TimeoutError()
    changes = 0

    async def changed():
        nonlocal changes
        changes += 1

    detector = FailureDetector(
        table=table,
        peer_client=peer,
        local_node_id="node-0",
        probe_interval_seconds=1.0,
        ping_timeout_seconds=0.25,
        indirect_timeout_seconds=0.5,
        indirect_probe_count=2,
        on_membership_change=changed,
        choose=lambda items: next(item for item in items if item.node_id == "node-1"),
    )
    await detector.run_once()
    assert (await table.get("node-1")).status is MemberStatus.SUSPECT  # type: ignore[union-attr]
    assert changes >= 1


@pytest.mark.asyncio
async def test_expired_suspicion_becomes_dead_before_next_probe():
    clock = FakeClock()
    local = member("node-0", 18000)
    target = member("node-1", 18001)
    table = MembershipTable(
        local,
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([target])
    await table.mark_suspect("node-1")
    clock.advance(3.1)
    peer = FakePeerClient()
    peer.direct["node-1"] = TimeoutError()
    detector = FailureDetector(
        table=table,
        peer_client=peer,
        local_node_id="node-0",
        probe_interval_seconds=1.0,
        ping_timeout_seconds=0.25,
        indirect_timeout_seconds=0.5,
        indirect_probe_count=0,
        on_membership_change=lambda: _noop(),
        choose=lambda items: items[0],
    )
    await detector.run_once()
    assert (await table.get("node-1")).status is MemberStatus.DEAD  # type: ignore[union-attr]


async def _noop() -> None:
    return None
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/unit/test_failure_detector.py
```

- [ ] **Step 3: Implement one probe iteration and background loop**

Create `src/distsys/cluster/failure_detector.py` with constructor fields from the tests plus `sleep=asyncio.sleep`. `run_once()` must:

```python
async def run_once(self) -> None:
    changed = await self.table.advance_timeouts_and_purge()
    if changed:
        await self.on_membership_change()

    candidates = await self.table.probe_candidates()
    if not candidates:
        return
    target = self.choose(list(candidates))
    snapshot = await self.table.snapshot()

    try:
        ack = await self.peer_client.ping(
            target,
            snapshot,
            timeout_seconds=self.ping_timeout_seconds,
        )
    except (ConnectionError, TimeoutError, OSError):
        ack = None

    if (
        ack is not None
        and ack.success
        and ack.target_node_id == target.node_id
    ):
        if await self.table.merge(ack.gossip):
            await self.on_membership_change()
        return

    helpers = [
        member
        for member in await self.table.alive_members(include_self=False)
        if member.node_id != target.node_id
    ]
    helpers = helpers[: self.indirect_probe_count]

    async def indirect(helper):
        try:
            return await self.peer_client.ping_request(
                helper,
                target,
                snapshot,
                timeout_seconds=self.indirect_timeout_seconds,
            )
        except (ConnectionError, TimeoutError, OSError):
            return None

    results = await asyncio.gather(*(indirect(helper) for helper in helpers))
    successful = next(
        (
            result
            for result in results
            if result is not None
            and result.success
            and result.target_node_id == target.node_id
        ),
        None,
    )
    if successful is not None:
        if await self.table.merge(successful.gossip):
            await self.on_membership_change()
        return

    if await self.table.mark_suspect(target.node_id):
        await self.on_membership_change()
```

`run()` is:

```python
async def run(self) -> None:
    while True:
        await self.run_once()
        await self.sleep(self.probe_interval_seconds)
```

Do not catch `asyncio.CancelledError` in `run()`; cancellation must propagate cleanly during shutdown.

- [ ] **Step 4: Verify GREEN**

```bash
python -m pytest -q tests/unit/test_failure_detector.py tests/unit/test_membership.py
python -m ruff check src/distsys/cluster/failure_detector.py tests/unit/test_failure_detector.py
python -m mypy src/distsys/cluster/failure_detector.py
```

- [ ] **Step 5: Commit**

```bash
git add src/distsys/cluster/failure_detector.py tests/unit/test_failure_detector.py
git commit -m "feat: add swim-lite failure detection"
```

---

### Task 10: Best-Effort Gossip Dissemination

**Files:**
- Create: `src/distsys/cluster/gossip.py`
- Create: `tests/unit/test_gossip.py`

**Interfaces:**
- Consumes: `MembershipTable`, `PeerClient`.
- Produces `GossipLoop.run_once()` and `GossipLoop.run()`.
- Gossip failures are swallowed after logging and do not mark suspicion.

- [ ] **Step 1: Write failing gossip tests**

Create `tests/unit/test_gossip.py`:

```python
import pytest

from distsys.cluster.codec import AckData
from distsys.cluster.gossip import GossipLoop
from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.membership import MembershipTable


def member(node_id: str, port: int, incarnation: int = 1):
    return ClusterMember(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        status=MemberStatus.ALIVE,
        incarnation=incarnation,
    )


class FakePeerClient:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def gossip(self, peer, members, *, timeout_seconds):
        self.calls.append(peer.node_id)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.mark.asyncio
async def test_gossip_merges_returned_snapshot():
    table = MembershipTable(
        member("node-0", 18000),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
    )
    await table.merge([member("node-1", 18001)])
    peer = FakePeerClient(
        AckData(True, "node-1", (member("node-1", 18001), member("node-2", 18002)))
    )
    changed = 0

    async def on_change():
        nonlocal changed
        changed += 1

    loop = GossipLoop(
        table=table,
        peer_client=peer,
        local_node_id="node-0",
        interval_seconds=1.0,
        timeout_seconds=0.25,
        on_membership_change=on_change,
        choose=lambda items: items[0],
    )
    await loop.run_once()
    assert await table.get("node-2") == member("node-2", 18002)
    assert changed == 1


@pytest.mark.asyncio
async def test_gossip_transport_failure_does_not_mark_peer_suspect():
    table = MembershipTable(
        member("node-0", 18000),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
    )
    await table.merge([member("node-1", 18001)])
    peer = FakePeerClient(ConnectionRefusedError())
    loop = GossipLoop(
        table=table,
        peer_client=peer,
        local_node_id="node-0",
        interval_seconds=1.0,
        timeout_seconds=0.25,
        on_membership_change=lambda: _noop(),
        choose=lambda items: items[0],
    )
    await loop.run_once()
    assert (await table.get("node-1")).status is MemberStatus.ALIVE  # type: ignore[union-attr]


async def _noop() -> None:
    return None
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/unit/test_gossip.py
```

- [ ] **Step 3: Implement gossip**

Create `src/distsys/cluster/gossip.py`. `run_once()` must select one alive peer excluding self, send the full snapshot once, merge returned gossip when successful, and only log on failure:

```python
async def run_once(self) -> None:
    peers = await self.table.alive_members(include_self=False)
    if not peers:
        return
    peer = self.choose(list(peers))
    snapshot = await self.table.snapshot()
    try:
        ack = await self.peer_client.gossip(
            peer,
            snapshot,
            timeout_seconds=self.timeout_seconds,
        )
    except (ConnectionError, TimeoutError, OSError):
        logger.debug(
            "cluster gossip failed",
            extra={"event": "cluster_gossip_failed", "peer_id": peer.node_id},
        )
        return
    if await self.table.merge(ack.gossip):
        await self.on_membership_change()
```

`run()` loops forever with `await self.sleep(self.interval_seconds)` and allows cancellation to propagate.

- [ ] **Step 4: Verify GREEN**

```bash
python -m pytest -q tests/unit/test_gossip.py
python -m ruff check src/distsys/cluster/gossip.py tests/unit/test_gossip.py
python -m mypy src/distsys/cluster/gossip.py
```

- [ ] **Step 5: Commit**

```bash
git add src/distsys/cluster/gossip.py tests/unit/test_gossip.py
git commit -m "feat: add cluster gossip dissemination"
```

---
### Task 11: Cluster Service — Bootstrap, Control Dispatch, Ring Synchronization, and Background Lifecycle

**Files:**
- Create: `src/distsys/cluster/service.py`
- Create: `tests/unit/test_cluster_service.py`

**Interfaces:**
- Consumes: `Settings`, `MembershipTable`, `ConsistentHashRing`, `PeerClient`, `FailureDetector`, `GossipLoop`, `ClusterRouter`, control codecs.
- Produces: `ClusterBootstrapError`.
- Produces: `ClusterService` with:
  - `start() -> None` (bootstrap, ring sync, start background loops)
  - `stop() -> None`
  - `sync_ring() -> None`
  - `handle_control(message: Message) -> Message`
  - `.router` for keyed task execution
  - `.membership` and `.ring` for integration/smoke inspection.

- [ ] **Step 1: Write failing service tests for seed bootstrap and control dispatch**

Create `tests/unit/test_cluster_service.py` with a fake peer client injected through the constructor:

```python
import pytest

from distsys.cluster.codec import AckData, decode_ack, decode_join_response, encode_join_request, encode_ping
from distsys.cluster.member import ClusterMember, MemberStatus, SeedAddress
from distsys.cluster.service import ClusterBootstrapError, ClusterService
from distsys.protocol.message import Message, MessageType
from distsys.resilience.deadline import Deadline
from distsys.utils.config import Settings


def member(node_id: str, port: int, incarnation: int = 10):
    return ClusterMember(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        status=MemberStatus.ALIVE,
        incarnation=incarnation,
    )


class FakePeerClient:
    def __init__(self) -> None:
        self.join_outcomes = {}
        self.ping_outcomes = {}

    async def join(self, seed, local_member, *, timeout_seconds):
        outcome = self.join_outcomes[(seed.host, seed.port)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def ping(self, peer, gossip, *, timeout_seconds):
        outcome = self.ping_outcomes[peer.node_id]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def ping_request(self, helper, target, gossip, *, timeout_seconds):
        raise AssertionError("not used in this test")

    async def gossip(self, peer, members, *, timeout_seconds):
        return AckData(True, peer.node_id, members)

    async def forward_task(self, peer, **kwargs):
        raise AssertionError("not used in this test")


async def local_execute(task_name, payload, deadline: Deadline):
    return {"task": task_name}


@pytest.mark.asyncio
async def test_seed_bootstrap_merges_snapshot_and_rebuilds_ring():
    settings = Settings(
        node_id="node-1",
        host="127.0.0.1",
        port=18001,
        cluster_enabled=True,
        cluster_seeds=(SeedAddress("127.0.0.1", 18000),),
    )
    peer = FakePeerClient()
    peer.join_outcomes[("127.0.0.1", 18000)] = (
        member("node-0", 18000),
        member("node-1", 18001, incarnation=20),
    )
    service = ClusterService(
        settings=settings,
        bound_port=18001,
        execute_local=local_execute,
        peer_client=peer,
        incarnation=20,
    )
    await service.bootstrap()
    assert {m.node_id for m in await service.membership.snapshot()} == {"node-0", "node-1"}
    assert {m.node_id for m in service.ring.candidates("key")} == {"node-0", "node-1"}


@pytest.mark.asyncio
async def test_configured_seed_failure_fails_bootstrap():
    settings = Settings(
        node_id="node-1",
        host="127.0.0.1",
        port=18001,
        cluster_enabled=True,
        cluster_seeds=(SeedAddress("127.0.0.1", 18000),),
    )
    peer = FakePeerClient()
    peer.join_outcomes[("127.0.0.1", 18000)] = ConnectionRefusedError()
    service = ClusterService(
        settings=settings,
        bound_port=18001,
        execute_local=local_execute,
        peer_client=peer,
        incarnation=20,
    )
    with pytest.raises(ClusterBootstrapError):
        await service.bootstrap()


@pytest.mark.asyncio
async def test_join_request_merges_member_and_returns_snapshot():
    settings = Settings(node_id="node-0", host="127.0.0.1", port=18000, cluster_enabled=True)
    service = ClusterService(
        settings=settings,
        bound_port=18000,
        execute_local=local_execute,
        peer_client=FakePeerClient(),
        incarnation=10,
    )
    joining = member("node-1", 18001, incarnation=20)
    request = Message.new_request(
        sender_id="node-1",
        msg_type=MessageType.JOIN_REQUEST,
        payload=encode_join_request(joining),
    )
    response = await service.handle_control(request)
    assert response.msg_type is MessageType.JOIN_RESPONSE
    assert {m.node_id for m in decode_join_response(response.payload)} == {"node-0", "node-1"}


@pytest.mark.asyncio
async def test_ping_merges_gossip_and_returns_ack_snapshot():
    settings = Settings(node_id="node-0", host="127.0.0.1", port=18000, cluster_enabled=True)
    service = ClusterService(
        settings=settings,
        bound_port=18000,
        execute_local=local_execute,
        peer_client=FakePeerClient(),
        incarnation=10,
    )
    remote = member("node-1", 18001, incarnation=20)
    request = Message.new_request(
        sender_id="node-1",
        msg_type=MessageType.PING,
        payload=encode_ping((remote,)),
    )
    response = await service.handle_control(request)
    ack = decode_ack(response.payload)
    assert response.msg_type is MessageType.ACK
    assert ack.success is True
    assert ack.target_node_id == "node-0"
    assert {m.node_id for m in ack.gossip} == {"node-0", "node-1"}
```

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/unit/test_cluster_service.py
```

- [ ] **Step 3: Implement service construction and ring synchronization**

`ClusterService.__init__()` accepts optional injected `peer_client` and `incarnation` for deterministic unit tests; production callers omit them. Construct:

```python
self.local_member = ClusterMember(
    node_id=settings.node_id,
    host=settings.host,
    port=bound_port,
    status=MemberStatus.ALIVE,
    incarnation=incarnation or fresh_incarnation(),
)
self.membership = MembershipTable(
    self.local_member,
    suspicion_timeout_seconds=settings.cluster_suspicion_timeout_seconds,
    dead_retention_seconds=settings.cluster_dead_retention_seconds,
)
self.ring = ConsistentHashRing(virtual_nodes=settings.cluster_virtual_nodes)
self.peer_client = peer_client or PeerClient(
    local_node_id=settings.node_id,
    retry_policy=RetryPolicy(
        max_attempts=settings.retry_max_attempts,
        base_delay_seconds=settings.retry_base_delay_seconds,
        max_delay_seconds=settings.retry_max_delay_seconds,
    ),
    circuit_breaker_failure_threshold=settings.circuit_breaker_failure_threshold,
    circuit_breaker_recovery_seconds=settings.circuit_breaker_recovery_seconds,
    max_frame_size=settings.max_frame_size,
)
self.router = ClusterRouter(
    local_node_id=settings.node_id,
    ring=self.ring,
    peer_client=self.peer_client,
    execute_local=execute_local,
)
self._ring_version = -1
self._background_tasks: set[asyncio.Task[None]] = set()
```

`sync_ring()` must rebuild only when membership version changes:

```python
async def sync_ring(self) -> None:
    version = self.membership.version
    if version == self._ring_version:
        return
    self.ring.rebuild(await self.membership.snapshot())
    self._ring_version = version
```

- [ ] **Step 4: Implement seed bootstrap**

`bootstrap()` behavior:

```python
async def bootstrap(self) -> None:
    await self.sync_ring()
    if not self.settings.cluster_seeds:
        return

    candidates = [
        seed
        for seed in self.settings.cluster_seeds
        if not (seed.host == self.local_member.host and seed.port == self.local_member.port)
    ]
    if not candidates:
        raise ClusterBootstrapError("configured cluster seeds contain only the local node")

    failures: list[BaseException] = []
    for seed in candidates:
        try:
            snapshot = await self.peer_client.join(
                seed,
                self.local_member,
                timeout_seconds=self.settings.cluster_ping_timeout_seconds,
            )
        except (ConnectionError, TimeoutError, OSError) as exc:
            failures.append(exc)
            continue
        await self.membership.merge(snapshot)
        await self.sync_ring()
        return

    raise ClusterBootstrapError("unable to contact any configured cluster seed") from failures[-1]
```

- [ ] **Step 5: Implement control dispatch**

`handle_control()` switches on message type and returns a normal `Message` using the original correlation id:

```python
async def handle_control(self, message: Message) -> Message:
    if message.msg_type is MessageType.JOIN_REQUEST:
        joining = decode_join_request(message.payload)
        await self.membership.merge((joining,))
        await self.sync_ring()
        payload = encode_join_response(await self.membership.snapshot())
        return Message.new_response(
            sender_id=self.settings.node_id,
            correlation_id=message.correlation_id,
            msg_type=MessageType.JOIN_RESPONSE,
            payload=payload,
        )

    if message.msg_type is MessageType.PING:
        incoming = decode_ping(message.payload)
        await self.membership.merge(incoming)
        await self.sync_ring()
        snapshot = await self.membership.snapshot()
        return Message.new_response(
            sender_id=self.settings.node_id,
            correlation_id=message.correlation_id,
            msg_type=MessageType.ACK,
            payload=encode_ack(
                success=True,
                target_node_id=self.settings.node_id,
                gossip=snapshot,
            ),
        )
```

For `PING_REQ`, merge incoming gossip, then call `peer_client.ping(target, current_snapshot, timeout_seconds=cluster_ping_timeout_seconds)`. Return `ACK(success=True, target_node_id=target.node_id, gossip=current_snapshot)` only when direct target ACK succeeds; on transport failure return `success=False`. Merge any returned target gossip before creating the helper ACK.

For `GOSSIP`, merge incoming members, sync the ring, and return `ACK(success=True, target_node_id=self.settings.node_id, gossip=current_snapshot)`.

Any other message type passed to `handle_control()` raises `ValueError`; `DistributedNode` only delegates supported control types.

- [ ] **Step 6: Wire detector/gossip background tasks**

Construct `FailureDetector` and `GossipLoop` with `on_membership_change=self.sync_ring`. Implement:

```python
async def start(self) -> None:
    await self.bootstrap()
    self._background_tasks = {
        asyncio.create_task(self.failure_detector.run(), name=f"{self.settings.node_id}-failure-detector"),
        asyncio.create_task(self.gossip_loop.run(), name=f"{self.settings.node_id}-gossip"),
    }


async def stop(self) -> None:
    tasks = list(self._background_tasks)
    self._background_tasks.clear()
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
```

- [ ] **Step 7: Verify GREEN**

```bash
python -m pytest -q \
  tests/unit/test_cluster_service.py \
  tests/unit/test_failure_detector.py \
  tests/unit/test_gossip.py
python -m ruff check src/distsys/cluster tests/unit/test_cluster_service.py
python -m mypy src/distsys/cluster
```

- [ ] **Step 8: Commit**

```bash
git add src/distsys/cluster/service.py tests/unit/test_cluster_service.py
git commit -m "feat: add cluster bootstrap and control service"
```

---

### Task 12: Integrate Cluster Routing into Client and Distributed Node

**Files:**
- Modify: `src/distsys/client.py`
- Modify: `src/distsys/node.py`
- Modify: `tests/integration/test_single_node.py`
- Modify: `tests/unit/test_codec.py` only if needed for updated typed decode callers.

**Interfaces:**
- `DistributedClient.request(task_name, payload, *, routing_key="")`.
- `DistributedClient.request_connected(task_name, payload, *, routing_key="")`.
- `DistributedNode.cluster_service: ClusterService | None`.
- Node-local helper: `_execute_local(task_name, payload, deadline) -> Any`.
- Startup order: executor -> TCP bind -> cluster service -> bootstrap/background loops -> ready.
- Shutdown order: cluster service -> listener/connections/handlers -> executor.

- [ ] **Step 1: Write failing standalone-compatibility and disabled-control tests**

Extend `tests/integration/test_single_node.py` using `unused_tcp_port` for any new fixture/test:

```python
from distsys.cluster.codec import encode_ping
from distsys.protocol.framing import encode_frame, read_message
from distsys.protocol.message import Message, MessageType


@pytest.mark.asyncio
async def test_routing_key_is_ignored_when_cluster_mode_is_disabled(unused_tcp_port):
    node = DistributedNode(
        Settings(node_id="standalone", host="127.0.0.1", port=unused_tcp_port)
    )
    await node.start()
    try:
        client = DistributedClient(port=unused_tcp_port)
        result = await client.request(
            "echo",
            {"message": "local"},
            routing_key="customer-123",
        )
        assert result == {"message": "local"}
    finally:
        await node.stop()


@pytest.mark.asyncio
async def test_cluster_control_is_rejected_when_cluster_mode_is_disabled(unused_tcp_port):
    node = DistributedNode(
        Settings(node_id="standalone", host="127.0.0.1", port=unused_tcp_port)
    )
    await node.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", unused_tcp_port)
        request = Message.new_request(
            sender_id="node-1",
            msg_type=MessageType.PING,
            payload=encode_ping(()),
        )
        writer.write(encode_frame(request))
        await writer.drain()
        response = await read_message(reader)
        decoded = decode_task_response(response.payload)
        assert response.msg_type is MessageType.ERROR
        assert decoded.error_code == messages_pb2.INVALID_REQUEST
        writer.close()
        await writer.wait_closed()
    finally:
        await node.stop()
```

Also add a regression test that `cluster.whoami` reports the local identity on an ordinary unkeyed request.

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/integration/test_single_node.py
```

Expected failures: client does not accept `routing_key`, default router does not yet register `cluster.whoami`, node does not classify cluster message types.

- [ ] **Step 3: Extend `DistributedClient` routing-key API**

Change `_round_trip()` to accept keyword-only `routing_key: str = ""` and call:

```python
request_payload = encode_task_request(
    task_name,
    payload,
    routing_key=routing_key,
)
```

Change public methods to:

```python
async def request(self, task_name: str, payload: Any, *, routing_key: str = "") -> Any:
```

```python
async def request_connected(
    self,
    task_name: str,
    payload: Any,
    *,
    routing_key: str = "",
) -> Any:
```

Pass the key into `_round_trip()` in both methods. Existing positional Phase-2 calls remain valid.

- [ ] **Step 4: Register the diagnostic task on the default router**

Change `_default_router` to accept the node id:

```python
@staticmethod
def _default_router(node_id: str) -> TaskRouter:
    router = TaskRouter()
    router.register("echo", echo_task)
    router.register("hash", hash_task)
    router.register("sort", sort_task)
    router.register("aggregate", aggregate_task)
    router.register("cluster.whoami", make_whoami_task(node_id))
    return router
```

Constructor uses `router or self._default_router(settings.node_id)`.

- [ ] **Step 5: Move admission control into `_execute_local()`**

Add:

```python
async def _execute_local(
    self,
    task_name: str,
    payload: object,
    deadline: Deadline,
) -> object:
    acquired = await self.backpressure.try_acquire()
    if not acquired:
        raise LocalOverloadedError("node is at execution capacity")
    try:
        return await self.executor.execute(task_name, payload, deadline=deadline)
    except WorkerPoolSaturatedError as exc:
        raise LocalOverloadedError("worker pool pending capacity is full") from exc
    finally:
        await self.backpressure.release()
```

Remove the old outer backpressure acquisition from `handle_message()`. This is essential: remote network waiting must not consume local execution capacity.

- [ ] **Step 6: Create/stop `ClusterService` in node lifecycle**

Add `self.cluster_service: ClusterService | None = None` in `__init__`.

After the TCP server binds in `start()`:

```python
if self.settings.cluster_enabled:
    self.cluster_service = ClusterService(
        settings=self.settings,
        bound_port=self.bound_port,
        execute_local=self._execute_local,
    )
    try:
        await self.cluster_service.start()
    except Exception:
        await self.cluster_service.stop()
        self.cluster_service = None
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        await self.executor.close()
        raise
```

In `stop()`, stop and clear `cluster_service` **before** closing the TCP listener.

- [ ] **Step 7: Split `handle_message()` by message class before rate limiting**

Implement this dispatch order:

```python
control_types = {
    MessageType.JOIN_REQUEST,
    MessageType.PING,
    MessageType.PING_REQ,
    MessageType.GOSSIP,
}

if message.msg_type in control_types:
    if self.cluster_service is None:
        return self._response(
            message,
            success=False,
            error_code=messages_pb2.INVALID_REQUEST,
            error_message="cluster mode is disabled",
        )
    try:
        return await self.cluster_service.handle_control(message)
    except DecodeError as exc:
        return self._response(
            message,
            success=False,
            error_code=messages_pb2.INVALID_REQUEST,
            error_message=str(exc),
        )
```

For `FORWARDED_REQUEST`:

1. Reject with `INVALID_REQUEST` when cluster mode is disabled.
2. `decode_forwarded_request()`.
3. If `remaining_timeout_ms <= 0`, return `TIMEOUT` without execution.
4. Create `Deadline.after(remaining_timeout_ms / 1000.0)`.
5. Call `_execute_local()` directly; do **not** consult the hash ring and do **not** call the public rate limiter.

For ordinary `REQUEST`:

1. Decode `TaskRequestData`.
2. Apply the public token bucket.
3. Create one `Deadline.after(settings.request_timeout_seconds)`.
4. If cluster service exists and `routing_key` is nonempty, call `cluster_service.router.execute()`.
5. Otherwise call `_execute_local()`.

- [ ] **Step 8: Map new cluster failures to structured errors**

Add exception mappings in node request handling:

```text
NoRouteError           -> NO_ROUTE
PeerUnavailableError   -> PEER_UNAVAILABLE
LocalOverloadedError   -> OVERLOADED
PeerApplicationError   -> preserve remote code/message
DeadlineExceeded       -> TIMEOUT
```

Keep the existing mappings for `UnknownTaskError`, `TaskValidationError`, `DecodeError`, worker-pool broken/closed failures, and internal errors.

- [ ] **Step 9: Verify GREEN and complete Phase-1/2 regression suite**

```bash
make proto
python -m pytest -q tests/integration/test_single_node.py
python -m pytest -q tests/unit tests/integration/test_compute_pipeline.py tests/integration/test_deadline_behavior.py tests/integration/test_event_loop_responsiveness.py tests/integration/test_overload_control.py tests/integration/test_single_node.py
python -m ruff check src tests scripts
python -m black --check src tests scripts
python -m mypy src/distsys
```

Expected: every pre-Phase-3 test plus the new standalone compatibility tests passes.

- [ ] **Step 10: Commit**

```bash
git add src/distsys/client.py src/distsys/node.py tests/integration/test_single_node.py
git commit -m "feat: integrate cluster-aware request dispatch"
```

---
### Task 13: Structured Cluster Event Logging

**Files:**
- Modify: `src/distsys/cluster/membership.py`
- Modify: `src/distsys/cluster/peer_client.py`
- Modify: `src/distsys/cluster/gossip.py`
- Modify: `src/distsys/cluster/cluster_router.py`
- Modify: `src/distsys/cluster/service.py`
- Create: `tests/unit/test_cluster_logging.py`

**Interfaces:**
- Uses the existing structured-logging convention: human message plus `extra={"event": ..., ...}`.
- Required INFO/WARNING events: `cluster_joined`, `membership_changed`, `member_suspect`, `member_dead`, `member_refuted`, `peer_forward`, `peer_forward_failed`, `route_failover`.
- Required DEBUG/WARNING gossip events: `cluster_gossip_sent`, `cluster_gossip_failed`.
- Successful PING/ACK chatter remains DEBUG or unlogged at INFO.

- [ ] **Step 1: Write failing logging tests**

Create `tests/unit/test_cluster_logging.py`:

```python
import logging

import pytest

from distsys.cluster.member import ClusterMember, MemberStatus
from distsys.cluster.membership import MembershipTable


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def member(node_id: str, status: MemberStatus = MemberStatus.ALIVE, incarnation: int = 10):
    return ClusterMember(
        node_id=node_id,
        host="127.0.0.1",
        port=18000 if node_id == "node-0" else 18001,
        status=status,
        incarnation=incarnation,
    )


def events(caplog) -> list[str]:
    return [
        getattr(record, "event")
        for record in caplog.records
        if hasattr(record, "event")
    ]


@pytest.mark.asyncio
async def test_membership_logs_suspect_dead_and_self_refutation(caplog):
    caplog.set_level(logging.INFO, logger="distsys.cluster.membership")
    clock = FakeClock()
    table = MembershipTable(
        member("node-0"),
        suspicion_timeout_seconds=3.0,
        dead_retention_seconds=30.0,
        clock=clock,
    )
    await table.merge([member("node-1")])
    await table.mark_suspect("node-1")
    clock.advance(3.1)
    await table.advance_timeouts_and_purge()
    await table.merge([member("node-0", MemberStatus.SUSPECT, incarnation=10)])

    recorded = events(caplog)
    assert "member_suspect" in recorded
    assert "member_dead" in recorded
    assert "member_refuted" in recorded
```

Add focused tests for router/peer/gossip/service while implementing those logs: use their existing fakes to force one forwarding failure, one failover, one gossip success/failure, and one successful seed bootstrap; assert the required `event` value appears in `caplog.records`. Do not assert human-readable log text.

- [ ] **Step 2: Verify RED**

```bash
python -m pytest -q tests/unit/test_cluster_logging.py
```

Expected: required structured events are not present yet.

- [ ] **Step 3: Add event logging at state ownership boundaries**

In `membership.py`, create `logger = logging.getLogger("distsys.cluster.membership")` and emit:

```python
logger.info(
    "member suspected",
    extra={"event": "member_suspect", "node_id": node_id},
)
```

when `mark_suspect()` changes `ALIVE -> SUSPECT`;

```python
logger.info(
    "member declared dead",
    extra={"event": "member_dead", "node_id": node_id},
)
```

when suspicion expires;

```python
refuted = replace(
    current,
    status=MemberStatus.ALIVE,
    incarnation=incoming.incarnation + 1,
)
self._members[self.local_node_id] = refuted
logger.info(
    "local member refuted suspicion",
    extra={
        "event": "member_refuted",
        "node_id": self.local_node_id,
        "incarnation": refuted.incarnation,
    },
)
```

when self-refutation creates a newer `ALIVE` record.

In `ClusterService.sync_ring()`, after a version change/rebuild, emit `membership_changed` with local node id, membership version, and alive-member count. After successful seed bootstrap emit `cluster_joined` with the seed endpoint.

In `PeerClient.forward_task()`, emit `peer_forward` before each logical forward and `peer_forward_failed` only when the logical forward exits with transport/open-circuit failure; do not log structured application failures as transport-health failures.

In `ClusterRouter.execute()`, emit `route_failover` whenever a candidate is skipped because of local overload, peer transport failure, open circuit, `OVERLOADED`, or `RATE_LIMITED`; include `from_node_id`, `routing_key`, and a short reason.

In `GossipLoop.run_once()`, emit `cluster_gossip_sent` at DEBUG on successful exchange and `cluster_gossip_failed` at DEBUG/WARNING on transport failure. Do not mark suspicion from gossip failures.

- [ ] **Step 4: Verify GREEN and ensure INFO logs are not probe-spam**

```bash
python -m pytest -q tests/unit/test_cluster_logging.py tests/unit/test_membership.py tests/unit/test_cluster_router.py tests/unit/test_gossip.py tests/unit/test_peer_client.py tests/unit/test_cluster_service.py
python -m ruff check src/distsys/cluster tests/unit/test_cluster_logging.py
python -m mypy src/distsys/cluster
```

Also inspect logger calls:

```bash
grep -R "cluster_gossip_sent\|PING\|ACK" -n src/distsys/cluster
```

Confirm normal successful PING/ACK operations are not emitted at INFO.

- [ ] **Step 5: Commit**

```bash
git add src/distsys/cluster tests/unit/test_cluster_logging.py
git commit -m "feat: add structured cluster event logging"
```

---

### Task 14: Three-Node Join and Gossip Convergence Integration

**Files:**
- Create: `tests/integration/cluster_helpers.py`
- Create: `tests/integration/test_cluster_join.py`
- Create: `tests/integration/test_gossip_convergence.py`

**Interfaces:**
- Test-only helper `wait_until(predicate, *, timeout_seconds, interval_seconds)`.
- Test-only `cluster_settings` returns conservative, fast-timing `Settings` for integration tests.
- All ports come from `unused_tcp_port_factory`.

- [ ] **Step 1: Create deterministic integration helpers**

Create `tests/integration/cluster_helpers.py`:

```python
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from distsys.cluster.member import SeedAddress
from distsys.utils.config import Settings


async def wait_until(
    predicate: Callable[[], Awaitable[bool]],
    *,
    timeout_seconds: float = 3.0,
    interval_seconds: float = 0.02,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        if await predicate():
            return
        if loop.time() >= deadline:
            raise AssertionError("condition did not become true before timeout")
        await asyncio.sleep(interval_seconds)


def cluster_settings(
    *,
    node_id: str,
    port: int,
    seeds: tuple[SeedAddress, ...] = (),
    rate_limit_rps: float = 10_000.0,
    rate_limit_burst: int = 1_000,
) -> Settings:
    return Settings(
        node_id=node_id,
        host="127.0.0.1",
        port=port,
        cpu_workers=1,
        cpu_queue_capacity=100,
        rate_limit_rps=rate_limit_rps,
        rate_limit_burst=rate_limit_burst,
        request_timeout_seconds=2.0,
        cluster_enabled=True,
        cluster_seeds=seeds,
        cluster_virtual_nodes=32,
        cluster_probe_interval_seconds=0.05,
        cluster_ping_timeout_seconds=0.03,
        cluster_indirect_timeout_seconds=0.05,
        cluster_indirect_probe_count=2,
        cluster_suspicion_timeout_seconds=0.20,
        cluster_dead_retention_seconds=1.0,
        cluster_gossip_interval_seconds=0.05,
    )
```

- [ ] **Step 2: Write failing three-node join test**

Create `tests/integration/test_cluster_join.py`:

```python
import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_three_nodes_bootstrap_to_same_alive_membership(unused_tcp_port_factory):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    node0 = DistributedNode(cluster_settings(node_id="node-0", port=ports[0]))
    node1 = DistributedNode(
        cluster_settings(
            node_id="node-1",
            port=ports[1],
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        )
    )
    node2 = DistributedNode(
        cluster_settings(
            node_id="node-2",
            port=ports[2],
            seeds=(SeedAddress("127.0.0.1", ports[0]),),
        )
    )
    nodes = [node0, node1, node2]
    try:
        for node in nodes:
            await node.start()

        async def converged() -> bool:
            for node in nodes:
                assert node.cluster_service is not None
                snapshot = await node.cluster_service.membership.snapshot()
                if len(snapshot) != 3:
                    return False
                if any(member.status is not MemberStatus.ALIVE for member in snapshot):
                    return False
            return True

        await wait_until(converged)
    finally:
        for node in reversed(nodes):
            await node.stop()
```

- [ ] **Step 3: Write failing gossip convergence test that requires dissemination beyond the original seed**

Create `tests/integration/test_gossip_convergence.py`:

```python
import pytest

from distsys.cluster.member import SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_seed_learns_about_node_joined_through_another_member(unused_tcp_port_factory):
    p0, p1, p2 = [unused_tcp_port_factory() for _ in range(3)]
    node0 = DistributedNode(cluster_settings(node_id="node-0", port=p0))
    node1 = DistributedNode(
        cluster_settings(
            node_id="node-1",
            port=p1,
            seeds=(SeedAddress("127.0.0.1", p0),),
        )
    )
    node2 = DistributedNode(
        cluster_settings(
            node_id="node-2",
            port=p2,
            seeds=(SeedAddress("127.0.0.1", p1),),
        )
    )
    nodes = [node0, node1, node2]
    try:
        for node in nodes:
            await node.start()

        async def node0_knows_node2() -> bool:
            assert node0.cluster_service is not None
            return await node0.cluster_service.membership.get("node-2") is not None

        await wait_until(node0_knows_node2)
    finally:
        for node in reversed(nodes):
            await node.stop()
```

- [ ] **Step 4: Verify RED before final service/node corrections**

```bash
python -m pytest -q \
  tests/integration/test_cluster_join.py \
  tests/integration/test_gossip_convergence.py
```

If either test fails, diagnose membership/control flow rather than weakening timing assertions. Do not increase timeouts until logs show the algorithm is correct but the environment is simply slower.

- [ ] **Step 5: Verify GREEN; stop on any failure**

If either acceptance test is still red, stop this task and use the systematic-debugging workflow against the already-specified implementation. Do not weaken convergence assertions or increase timing values as a substitute for a missing state transition. Resume only after the root cause is fixed in the component that owns it.

- [ ] **Step 6: Re-run both acceptance tests together**

```bash
python -m pytest -q \
  tests/integration/test_cluster_join.py \
  tests/integration/test_gossip_convergence.py
```

Expected: `2 passed`.

- [ ] **Step 7: Commit**

```bash
git add tests/integration/cluster_helpers.py tests/integration/test_cluster_join.py tests/integration/test_gossip_convergence.py src/distsys
git commit -m "test: prove cluster bootstrap and gossip convergence"
```

---

### Task 15: Failure Detection, Distributed Routing, Failover, Rejoin, and Control-Plane Isolation

**Files:**
- Create: `tests/integration/test_failure_detection.py`
- Create: `tests/integration/test_distributed_routing.py`
- Create: `tests/integration/test_routing_failover.py`
- Create: `tests/integration/test_node_rejoin.py`
- Create: `tests/integration/test_cluster_control_under_load.py`

**Interfaces:**
- Uses the real `DistributedNode`, real TCP peer exchanges, real membership table, and real consistent hash ring.
- Proves the exit criteria end-to-end rather than by mocks.

- [ ] **Step 1: Write failing failure-detection test**

Create `tests/integration/test_failure_detection.py`:

```python
import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_stopped_node_transitions_to_suspect_then_dead(unused_tcp_port_factory):
    p0, p1 = [unused_tcp_port_factory() for _ in range(2)]
    node0 = DistributedNode(cluster_settings(node_id="node-0", port=p0))
    node1 = DistributedNode(
        cluster_settings(
            node_id="node-1",
            port=p1,
            seeds=(SeedAddress("127.0.0.1", p0),),
        )
    )
    try:
        await node0.start()
        await node1.start()
        assert node0.cluster_service is not None

        async def joined() -> bool:
            return await node0.cluster_service.membership.get("node-1") is not None

        await wait_until(joined)
        await node1.stop()

        async def suspect() -> bool:
            current = await node0.cluster_service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.SUSPECT

        await wait_until(suspect, timeout_seconds=2.0)
        assert all(
            member.node_id != "node-1"
            for member in node0.cluster_service.ring.candidates("any-key")
        )

        async def dead() -> bool:
            current = await node0.cluster_service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.DEAD

        await wait_until(dead, timeout_seconds=2.0)
    finally:
        await node1.stop()
        await node0.stop()
```

- [ ] **Step 2: Write failing distributed-routing proof**

Create `tests/integration/test_distributed_routing.py`:

```python
import pytest

from distsys.client import DistributedClient
from distsys.cluster.member import SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_keyed_request_executes_on_calculated_remote_owner(unused_tcp_port_factory):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    nodes = [
        DistributedNode(cluster_settings(node_id="node-0", port=ports[0])),
        DistributedNode(
            cluster_settings(
                node_id="node-1",
                port=ports[1],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
        DistributedNode(
            cluster_settings(
                node_id="node-2",
                port=ports[2],
                seeds=(SeedAddress("127.0.0.1", ports[0]),),
            )
        ),
    ]
    try:
        for node in nodes:
            await node.start()

        async def converged() -> bool:
            return all(
                node.cluster_service is not None
                and len(await node.cluster_service.membership.alive_members()) == 3
                for node in nodes
            )

        await wait_until(converged)
        service = nodes[0].cluster_service
        assert service is not None
        key = next(
            f"customer-{i}"
            for i in range(10_000)
            if service.ring.owner(f"customer-{i}").node_id != "node-0"
        )
        expected_owner = service.ring.owner(key).node_id
        client = DistributedClient(port=ports[0])
        result = await client.request("cluster.whoami", {}, routing_key=key)
        assert result == {"node_id": expected_owner}
    finally:
        for node in reversed(nodes):
            await node.stop()
```

When implementing the test, avoid an async generator expression inside `all()` if type checking rejects it; use an explicit `for` loop returning `False` on the first non-converged node. The semantic assertion remains exactly “all three nodes report three alive members.”

- [ ] **Step 3: Write failing routing failover test**

Create `tests/integration/test_routing_failover.py`:

```python
import pytest

from distsys.client import DistributedClient
from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_failed_primary_owner_is_removed_and_next_candidate_executes(unused_tcp_port_factory):
    ports = [unused_tcp_port_factory() for _ in range(3)]
    nodes = [
        DistributedNode(cluster_settings(node_id="node-0", port=ports[0])),
        DistributedNode(cluster_settings(node_id="node-1", port=ports[1], seeds=(SeedAddress("127.0.0.1", ports[0]),))),
        DistributedNode(cluster_settings(node_id="node-2", port=ports[2], seeds=(SeedAddress("127.0.0.1", ports[0]),))),
    ]
    try:
        for node in nodes:
            await node.start()
        service = nodes[0].cluster_service
        assert service is not None

        async def converged() -> bool:
            return len(await service.membership.alive_members()) == 3

        await wait_until(converged)
        key = next(
            f"failover-{i}"
            for i in range(10_000)
            if service.ring.owner(f"failover-{i}").node_id == "node-2"
        )
        client = DistributedClient(port=ports[0])
        assert await client.request("cluster.whoami", {}, routing_key=key) == {"node_id": "node-2"}

        await nodes[2].stop()

        async def removed_from_ownership() -> bool:
            current = await service.membership.get("node-2")
            if current is None or current.status is MemberStatus.ALIVE:
                return False
            return service.ring.owner(key).node_id != "node-2"

        await wait_until(removed_from_ownership, timeout_seconds=2.0)
        result = await client.request("cluster.whoami", {}, routing_key=key)
        assert result["node_id"] in {"node-0", "node-1"}
    finally:
        for node in reversed(nodes):
            await node.stop()
```

- [ ] **Step 4: Write failing rejoin test with newer incarnation**

Create `tests/integration/test_node_rejoin.py`:

```python
import pytest

from distsys.cluster.member import MemberStatus, SeedAddress
from distsys.node import DistributedNode
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_restarted_node_with_newer_incarnation_rejoins(unused_tcp_port_factory):
    p0, p1 = [unused_tcp_port_factory() for _ in range(2)]
    node0 = DistributedNode(cluster_settings(node_id="node-0", port=p0))
    node1 = DistributedNode(cluster_settings(node_id="node-1", port=p1, seeds=(SeedAddress("127.0.0.1", p0),)))
    restarted = None
    try:
        await node0.start()
        await node1.start()
        service = node0.cluster_service
        assert service is not None

        async def joined() -> bool:
            return await service.membership.get("node-1") is not None

        await wait_until(joined)
        original = await service.membership.get("node-1")
        assert original is not None
        old_incarnation = original.incarnation
        await node1.stop()

        async def dead() -> bool:
            current = await service.membership.get("node-1")
            return current is not None and current.status is MemberStatus.DEAD

        await wait_until(dead, timeout_seconds=2.0)

        restarted = DistributedNode(
            cluster_settings(
                node_id="node-1",
                port=p1,
                seeds=(SeedAddress("127.0.0.1", p0),),
            )
        )
        await restarted.start()

        async def rejoined() -> bool:
            current = await service.membership.get("node-1")
            return (
                current is not None
                and current.status is MemberStatus.ALIVE
                and current.incarnation > old_incarnation
            )

        await wait_until(rejoined, timeout_seconds=2.0)
    finally:
        if restarted is not None:
            await restarted.stop()
        await node1.stop()
        await node0.stop()
```

- [ ] **Step 5: Write control-plane-under-load test**

Create `tests/integration/test_cluster_control_under_load.py`:

```python
import pytest

from distsys.client import DistributedClient, RemoteTaskError
from distsys.cluster.member import SeedAddress
from distsys.node import DistributedNode
from distsys.proto import messages_pb2
from tests.integration.cluster_helpers import cluster_settings, wait_until


@pytest.mark.asyncio
async def test_ping_still_works_after_public_rate_limit_rejects_task(unused_tcp_port_factory):
    p0, p1 = [unused_tcp_port_factory() for _ in range(2)]
    node0 = DistributedNode(
        cluster_settings(
            node_id="node-0",
            port=p0,
            rate_limit_rps=0.01,
            rate_limit_burst=1,
        )
    )
    node1 = DistributedNode(
        cluster_settings(
            node_id="node-1",
            port=p1,
            seeds=(SeedAddress("127.0.0.1", p0),),
        )
    )
    try:
        await node0.start()
        await node1.start()
        service0 = node0.cluster_service
        service1 = node1.cluster_service
        assert service0 is not None and service1 is not None

        async def joined() -> bool:
            return await service0.membership.get("node-1") is not None

        await wait_until(joined)
        client = DistributedClient(port=p0)
        assert await client.request("echo", {"id": 1}) == {"id": 1}
        with pytest.raises(RemoteTaskError) as exc:
            await client.request("echo", {"id": 2})
        assert exc.value.code == messages_pb2.RATE_LIMITED

        remote = await service0.membership.get("node-1")
        assert remote is not None
        ack = await service0.peer_client.ping(
            remote,
            await service0.membership.snapshot(),
            timeout_seconds=0.2,
        )
        assert ack.success is True
        assert ack.target_node_id == "node-1"
    finally:
        await node1.stop()
        await node0.stop()
```

- [ ] **Step 6: Run each acceptance test independently**

Run in this order so failures are isolated:

```bash
python -m pytest -q tests/integration/test_failure_detection.py
python -m pytest -q tests/integration/test_distributed_routing.py
python -m pytest -q tests/integration/test_routing_failover.py
python -m pytest -q tests/integration/test_node_rejoin.py
python -m pytest -q tests/integration/test_cluster_control_under_load.py
```

For each failure, use the systematic-debugging workflow: inspect logs/state transition first, form one hypothesis, make one production change, rerun that test, then rerun the previously green Phase-3 tests.

- [ ] **Step 7: Run all Phase-3 integration tests together**

```bash
python -m pytest -q \
  tests/integration/test_cluster_join.py \
  tests/integration/test_gossip_convergence.py \
  tests/integration/test_failure_detection.py \
  tests/integration/test_distributed_routing.py \
  tests/integration/test_routing_failover.py \
  tests/integration/test_node_rejoin.py \
  tests/integration/test_cluster_control_under_load.py
```

Expected: all Phase-3 integration tests pass repeatedly in one process.

- [ ] **Step 8: Commit**

```bash
git add tests/integration src/distsys
git commit -m "test: validate distributed routing and failure recovery"
```

---

### Task 16: Local Three-Node Runner, Phase-3 Smoke, Documentation, and Release Gate

**Files:**
- Create: `scripts/run_phase3_cluster.sh`
- Create: `scripts/phase3_smoke.py`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `docs/PHASES.md`
- Create: `docs/PHASE3_VERIFICATION.md`
- Create: `docs/PHASE3_FILE_MANIFEST.md`
- Modify: `pyproject.toml`
- Modify: `src/distsys/__init__.py`

**Interfaces:**
- `make phase3-cluster` runs the local runner.
- `make phase3-smoke` runs the smoke workflow against ports 18000/18001/18002.
- Runner refuses to start if required ports are occupied and only kills child PIDs it created.
- Smoke proves membership convergence and remote keyed execution; managed failure/restart mode only stops subprocesses it launched itself.

- [ ] **Step 1: Create the three-node runner with port ownership safety**

Create executable `scripts/run_phase3_cluster.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${PHASE3_LOG_DIR:-$ROOT/.phase3-logs}"
mkdir -p "$LOG_DIR"

for port in 18000 18001 18002; do
  if ss -ltn "sport = :$port" | grep -q LISTEN; then
    echo "port $port is already in use; refusing to start cluster" >&2
    exit 1
  fi
done

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  wait || true
}
trap cleanup EXIT INT TERM

start_node() {
  local node_id="$1"
  local port="$2"
  local seeds="$3"
  env \
    NODE_ID="$node_id" \
    NODE_HOST=127.0.0.1 \
    NODE_PORT="$port" \
    CPU_WORKERS=1 \
    CPU_QUEUE_CAPACITY=100 \
    RATE_LIMIT_RPS=500 \
    RATE_LIMIT_BURST=100 \
    REQUEST_TIMEOUT_SECONDS=5 \
    CLUSTER_ENABLED=true \
    CLUSTER_SEEDS="$seeds" \
    CLUSTER_VIRTUAL_NODES=64 \
    CLUSTER_PROBE_INTERVAL_SECONDS=1.0 \
    CLUSTER_PING_TIMEOUT_SECONDS=0.25 \
    CLUSTER_INDIRECT_TIMEOUT_SECONDS=0.50 \
    CLUSTER_INDIRECT_PROBE_COUNT=2 \
    CLUSTER_SUSPICION_TIMEOUT_SECONDS=3.0 \
    CLUSTER_DEAD_RETENTION_SECONDS=30.0 \
    CLUSTER_GOSSIP_INTERVAL_SECONDS=1.0 \
    LOG_LEVEL=INFO \
    python -m distsys.main >"$LOG_DIR/$node_id.log" 2>&1 &
  pids+=("$!")
}

start_node node-0 18000 ""
sleep 0.3
start_node node-1 18001 "127.0.0.1:18000"
start_node node-2 18002 "127.0.0.1:18000"

echo "Phase-3 cluster running. Logs: $LOG_DIR"
echo "PIDs: ${pids[*]}"
wait
```

Make executable:

```bash
chmod +x scripts/run_phase3_cluster.sh
```

- [ ] **Step 2: Create a smoke script that never kills arbitrary machine processes**

Create `scripts/phase3_smoke.py` with CLI:

```text
python scripts/phase3_smoke.py --host 127.0.0.1 --ports 18000 18001 18002
```

The script must:

1. Construct `PeerClient` using the normal Phase-2 retry/breaker settings.
2. Direct-ping each node using known `ClusterMember` endpoints and collect ACK snapshots.
3. Poll until each returned snapshot contains `node-0`, `node-1`, `node-2` as `ALIVE`.
4. Build a local `ConsistentHashRing(virtual_nodes=64)` from the snapshot.
5. Find at least one key owned by a node other than `node-0`.
6. Send `cluster.whoami` through `DistributedClient(port=18000)` with that routing key.
7. Assert returned `node_id` equals the calculated owner.
8. Check 100 sample keys and assert at least two distinct physical owners occur.
9. Print a concise PASS summary and exit zero; raise/exit nonzero on any mismatch.

For failure/restart demonstration, add optional `--managed-command` mode that launches `scripts/run_phase3_cluster.sh` itself and records only its own subprocess handle. It may terminate that managed subprocess for the failure scenario; without this option it is inspection-only and must not discover/kill PIDs from `ss`, `lsof`, or `/proc`.

- [ ] **Step 3: Add Makefile targets**

Add to `.PHONY` and targets:

```make
phase3-cluster:
	bash scripts/run_phase3_cluster.sh

phase3-smoke:
	$(PYTHON) scripts/phase3_smoke.py --host 127.0.0.1 --ports 18000 18001 18002
```

- [ ] **Step 4: Update README and phase documentation with defensible claims**

`README.md` must document:

```text
Phase 3 delivery semantics:
best-effort keyed routing with bounded transport retries and failover for stateless/idempotent work.
```

It must explicitly state that Phase 3 does **not** implement exactly-once execution, consensus, replicated application state, or durable membership.

Document the local three-terminal/runner workflow and the conservative laptop profile (`CPU_WORKERS=1` for each of three nodes).

Update `docs/PHASES.md` to mark Phase 3 implemented only after the final gates below pass.

Set release metadata to `0.3.0` in `pyproject.toml` and `src/distsys/__init__.py`; do not change dependency versions because Phase 3 adds no runtime dependency.

Create `docs/PHASE3_FILE_MANIFEST.md` listing every Phase-3 new/modified file and `docs/PHASE3_VERIFICATION.md` recording commands and actual observed results. Do not insert benchmark numbers until they are measured on the final tree.

- [ ] **Step 5: Run the complete automated quality gate**

```bash
make proto
make quality
```

Required:

```text
all Phase-1 tests pass
all Phase-2 tests pass
all Phase-3 tests pass
Ruff: clean
Black: clean
mypy: clean
```

Record the exact test count in `docs/PHASE3_VERIFICATION.md` only after this run.

- [ ] **Step 6: Run the real three-node laptop smoke**

Terminal 1:

```bash
source .venv/bin/activate
bash scripts/run_phase3_cluster.sh
```

Terminal 2:

```bash
source .venv/bin/activate
python scripts/phase3_smoke.py --host 127.0.0.1 --ports 18000 18001 18002
```

Required smoke evidence:

```text
all 3 endpoints reachable
all 3 snapshots converge to 3 ALIVE members
consistent-hash owner calculation agrees with routed cluster.whoami result
100 sample keys map to at least 2 physical nodes
0 smoke assertion failures
```

Do not advertise throughput/latency from this smoke; performance benchmarking belongs to Phase 6.

- [ ] **Step 7: Verify shutdown leaves no Phase-3 ports occupied**

After stopping the runner:

```bash
for port in 18000 18001 18002; do
  ss -ltnp | grep ":$port" && exit 1 || true
done
echo "Phase-3 ports are free"
```

- [ ] **Step 8: Commit scripts and documentation**

```bash
git add \
  scripts/run_phase3_cluster.sh \
  scripts/phase3_smoke.py \
  Makefile \
  README.md \
  docs/PHASES.md \
  docs/PHASE3_FILE_MANIFEST.md \
  docs/PHASE3_VERIFICATION.md \
  pyproject.toml \
  src/distsys/__init__.py

git commit -m "docs: complete phase three cluster validation"
```

- [ ] **Step 9: Final branch verification before PR/tag**

```bash
git status --short
git log --oneline --decorate v0.2.0..HEAD
make quality
```

Required: clean working tree and a fresh green quality gate.

Push the feature branch:

```bash
git push -u origin phase/3-distributed-cluster
```

Create a PR to `main`. Do not create `v0.3.0` on the feature branch. After the PR is merged:

```bash
git switch main
git pull origin main
make quality

git tag -a v0.3.0 -m "Phase 3: distributed cluster routing and failure detection"
git push origin v0.3.0
```

---

## Recommended Commit Sequence

```text
feat: add cluster membership domain types
feat: add incarnation-aware membership table
feat: extend protocol for cluster control and routing
feat: add deterministic consistent hash ring
feat: add cluster runtime configuration
feat: add cluster routing diagnostic task
feat: add resilient peer transport
feat: add consistent-hash cluster routing
feat: add swim-lite failure detection
feat: add cluster gossip dissemination
feat: add cluster bootstrap and control service
feat: integrate cluster-aware request dispatch
feat: add structured cluster event logging
test: prove cluster bootstrap and gossip convergence
test: validate distributed routing and failure recovery
docs: complete phase three cluster validation
```

## Plan Self-Review

- **Spec coverage:** Tasks 1–16 cover every production component, protocol addition, configuration rule, logging event, integration scenario, smoke workflow, and release gate in the approved specification.
- **Placeholder scan:** no `TBD`, `TODO`, ellipsis implementation bodies, “similar to,” or unspecified error-handling steps remain.
- **Type/interface consistency:** `ClusterMember`, `MembershipTable`, `TaskRequestData`, `AckData`, `ForwardedTaskData`, `PeerClient`, `ClusterRouter`, `FailureDetector`, `GossipLoop`, and `ClusterService` use the same signatures across producer and consumer tasks.
- **Compatibility:** existing message/error numeric values remain unchanged; cluster mode defaults off; unkeyed requests remain local.
- **Deadline clarification:** the spec now states that retries keep one logical correlation id while rebuilding only the forwarded payload’s `remaining_timeout_ms` from the current shared deadline. This is a precision clarification, not an architecture change.
- **Scope:** no Phase-4/5/6 infrastructure has leaked into Phase 3.

## Completion Checklist

Before declaring Phase 3 complete, verify each item with fresh command output:

- [ ] `v0.2.0` is an ancestor of the Phase-3 branch.
- [ ] Static-seed bootstrap forms a three-node cluster.
- [ ] Gossip converges membership through non-seed paths.
- [ ] Direct probe succeeds for a healthy peer.
- [ ] Failed direct probe triggers indirect probe.
- [ ] Failed direct + indirect probes produce `SUSPECT`.
- [ ] Suspicion timeout produces `DEAD`.
- [ ] Self-suspicion/self-dead gossip refutes with higher `ALIVE` incarnation.
- [ ] Dead tombstone blocks same-incarnation stale resurrection.
- [ ] Dead tombstone purges after retention.
- [ ] Restarted same `node_id` rejoins with newer incarnation.
- [ ] SHA-256 ownership is deterministic across identical membership.
- [ ] Default production ring uses 64 virtual nodes.
- [ ] `SUSPECT` and `DEAD` members are excluded from ownership.
- [ ] Unkeyed Phase-2 requests remain local and backward compatible.
- [ ] Keyed local-owner requests execute locally.
- [ ] Keyed remote-owner requests forward one hop and execute remotely.
- [ ] Forwarded requests never consult the ring again.
- [ ] Transport failures use bounded full-jitter retry within one deadline.
- [ ] Per-peer task circuit breakers do not count structured application responses as transport failures.
- [ ] `OVERLOADED`/transport/open-circuit candidate failures can fail over.
- [ ] `INVALID_REQUEST`, `UNKNOWN_TASK`, `INTERNAL_ERROR`, and `TIMEOUT` are not replayed to another candidate.
- [ ] Cluster control bypasses public task rate limiting/backpressure.
- [ ] Required structured cluster events are emitted without INFO-level successful PING spam.
- [ ] Every new network integration test uses `unused_tcp_port_factory`.
- [ ] `make quality` passes on the final tree.
- [ ] Three-node laptop smoke passes with no assertion failures.
- [ ] Shutdown releases ports 18000, 18001, and 18002.
- [ ] README states best-effort/idempotent semantics and does not claim exactly-once execution.
- [ ] `v0.3.0` is created only from merged, re-verified `main`.
