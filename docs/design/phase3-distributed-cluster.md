# Phase 3 Distributed Cluster Design

> **Document status:** Historical design record. Phase 3 is implemented and verified. This file preserves the original specification; see the [current architecture](../architecture/phase3-distributed-cluster.md) and [verification record](../verification/phase3.md).

**Historical planning status:** Approved written specification  
**Target release:** `v0.3.0`  
**Base release:** `v0.2.0`  
**Feature branch:** `phase/3-distributed-cluster`

## 1. Goal

Phase 3 turns the Phase-2 single-node runtime into a small, decentralized cluster that can:

- bootstrap from static seed addresses,
- converge membership through gossip,
- detect failures with SWIM-style direct and indirect probes,
- maintain `ALIVE -> SUSPECT -> DEAD` membership state using incarnation numbers,
- deterministically route keyed work with a SHA-256 consistent hash ring,
- forward a request to one remote owner without routing loops,
- reuse Phase-2 deadlines, retries, and circuit breakers for peer task calls,
- fail over idempotent/stateless workloads to the next healthy routing candidate,
- remove unhealthy nodes from new ownership and admit restarted nodes with newer incarnations,
- remain fully backward compatible as a standalone Phase-2 node when clustering is disabled.

The Phase-3 cluster is intentionally decentralized. It does not introduce etcd, replicated application state, CRDTs, TLS, Prometheus, Kubernetes, or Terraform.

## 2. Baseline and compatibility constraints

Phase 3 starts from the verified `v0.2.0` baseline.

The following Phase-2 behavior must remain valid:

- TCP framing stays version 1 with the existing fixed 8-byte header.
- `REQUEST = 1`, `RESPONSE = 2`, `ERROR = 3`, and `HEARTBEAT = 4` are not renumbered.
- Existing clients that call `request(task_name, payload)` without a routing key execute using the existing local path.
- Existing tasks `echo`, `hash`, `sort`, and `aggregate` keep their current input/output contracts.
- Existing structured error codes 0 through 6 keep their numeric values.
- Phase-1 and Phase-2 tests remain green.
- Cluster mode defaults to disabled.

Python remains 3.12+, Protobuf remains the wire serialization format, and asyncio remains the networking runtime.

## 3. Topology and resource profile

The development cluster uses one TCP endpoint per node. Client traffic, peer task traffic, and cluster control traffic share that endpoint and are separated by `MessageType`.

```text
                         CLIENT
                           |
                           v
                    +-------------+
                    |   node-0    |
                    | 127.0.0.1   |
                    |   :18000    |
                    +------+------+ 
                           |
                      routing_key
                           |
                           v
                  ConsistentHashRing
                           |
                 +---------+---------+
                 |                   |
              local              remote
                 |                   |
                 v                   v
           TaskExecutor          PeerClient
                                     |
                              deadline + retry
                              + circuit breaker
                                     |
                                     v
                              +-------------+
                              |   node-1    |
                              |   :18001    |
                              +-------------+

Membership/control plane:

node-0 <------ PING / ACK / GOSSIP ------> node-1
   ^                                         ^
   |                                         |
   +------ PING / ACK / GOSSIP ----------> node-2
                                             :18002
```

Laptop defaults when all three nodes run simultaneously:

- 3 nodes: ports 18000, 18001, 18002.
- `CPU_WORKERS=1` per node.
- `CPU_QUEUE_CAPACITY=100` per node.
- `RATE_LIMIT_RPS=500` per node.
- `RATE_LIMIT_BURST=100` per node.
- Probe interval: 1.0 second.
- Gossip interval: 1.0 second.

Single-node development may continue to use `CPU_WORKERS=2`.

## 4. Bootstrap model

The selected model is **static seed bootstrap plus decentralized gossip membership**.

A seed address is `host:port`. Seeds are not permanent leaders and do not remain special after bootstrap.

Example:

```text
node-0:
  CLUSTER_ENABLED=true
  CLUSTER_SEEDS=

node-1:
  CLUSTER_ENABLED=true
  CLUSTER_SEEDS=127.0.0.1:18000

node-2:
  CLUSTER_ENABLED=true
  CLUSTER_SEEDS=127.0.0.1:18000
```

Startup order for a joining node:

1. Start its TCP server so it can receive probes immediately.
2. Create its local membership record as `ALIVE` with a fresh incarnation.
3. Try configured seeds in order, skipping a seed that resolves to the node itself.
4. Send `JOIN_REQUEST` containing the joining member record.
5. The seed merges the member and returns `JOIN_RESPONSE` with its complete membership snapshot, including retained `DEAD` tombstones.
6. The joining node merges the response.
7. Start failure-detector and gossip background loops.

If `CLUSTER_ENABLED=true`, at least one seed is configured, and no seed can be contacted, startup fails. The node must not silently form an independent cluster.

A seedless cluster-enabled node is allowed and forms the initial cluster root.

Concurrent live processes using the same `node_id` are unsupported. A newer incarnation takes precedence and effectively replaces the older identity.

## 5. Message types

Extend `MessageType` without changing existing numeric values:

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

All cluster-control exchanges are request/response interactions over the existing framed TCP protocol:

- `JOIN_REQUEST -> JOIN_RESPONSE`
- `PING -> ACK`
- `PING_REQ -> ACK`
- `GOSSIP -> ACK`

`FORWARDED_REQUEST` receives the normal task `RESPONSE` or `ERROR` message type.

## 6. Protobuf schema additions

Existing messages remain wire compatible. New fields are appended using unused field numbers.

### 6.1 Error codes

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
```

### 6.2 Membership status

```proto
enum MemberStatus {
  MEMBER_STATUS_UNSPECIFIED = 0;
  ALIVE = 1;
  SUSPECT = 2;
  DEAD = 3;
}
```

### 6.3 Member record

```proto
message ClusterMember {
  string node_id = 1;
  string host = 2;
  uint32 port = 3;
  MemberStatus status = 4;
  uint64 incarnation = 5;
}
```

### 6.4 Join

```proto
message JoinRequest {
  ClusterMember member = 1;
}

message JoinResponse {
  repeated ClusterMember members = 1;
}
```

### 6.5 Probe and acknowledgement

```proto
message Ping {
  repeated ClusterMember gossip = 1;
}

message Ack {
  bool success = 1;
  string target_node_id = 2;
  repeated ClusterMember gossip = 3;
}
```

For a direct `PING`, `success=true` means the receiver is reachable and `target_node_id` identifies the receiver.

For a `PING_REQ`, the helper returns `success=true` only when it successfully receives an `ACK` from the requested target. A helper that cannot reach the target returns `success=false` rather than inventing a positive acknowledgement.

### 6.6 Indirect probe

```proto
message PingRequest {
  ClusterMember target = 1;
  repeated ClusterMember gossip = 2;
}
```

### 6.7 Gossip

```proto
message Gossip {
  repeated ClusterMember members = 1;
}
```

The receiver merges the snapshot and returns an `ACK` containing its own current snapshot. Gossip is best effort and is not retried by the gossip loop.

### 6.8 Routed task request

Append a routing field:

```proto
message TaskRequest {
  string task_name = 1;
  bytes payload_json = 2;
  string routing_key = 3;
}
```

An empty routing key preserves Phase-2 local execution.

### 6.9 Forwarded task request

```proto
message ForwardedTaskRequest {
  TaskRequest request = 1;
  string origin_node_id = 2;
  uint32 remaining_timeout_ms = 3;
}
```

`remaining_timeout_ms` carries a duration, not a wall-clock deadline, avoiding clock-synchronization assumptions. The receiver creates a new local monotonic deadline from this remaining budget.

A forwarded request is never routed again. It always executes locally at the receiver.

## 7. Domain membership model

### 7.1 `MemberStatus`

Domain code uses a Python enum with the same ordering semantics:

```text
ALIVE = 1
SUSPECT = 2
DEAD = 3
```

The numeric ordering is intentional because, for equal incarnations, greater severity wins.

### 7.2 `ClusterMember`

The domain record contains:

- `node_id: str`
- `host: str`
- `port: int`
- `status: MemberStatus`
- `incarnation: int`

Network address changes are accepted only with a strictly newer incarnation. Equal-incarnation state updates may change status severity but do not replace host/port.

### 7.3 `SeedAddress`

A seed parser validates `host:port`, rejects empty hosts, and requires ports in 1..65535.

## 8. Incarnation numbers and merge rules

A node starts with `time.time_ns()` as its Phase-3 incarnation value. Durable incarnation recovery is deferred to the persistence/recovery phase.

For a membership update about a non-local node:

1. Unknown `node_id`: accept it.
2. Incoming incarnation lower than local: ignore it.
3. Incoming incarnation higher than local: accept the complete incoming record.
4. Equal incarnation: the more severe status wins: `ALIVE < SUSPECT < DEAD`.
5. Equal incarnation and equal status: retain the existing host/port.

### 8.1 Self-refutation

A node never accepts a `SUSPECT` or `DEAD` state for itself as final truth.

If incoming gossip says the local node is `SUSPECT` or `DEAD` at incarnation `N`, and `N >= local.incarnation`, the local node sets:

```text
incarnation = N + 1
status = ALIVE
```

That new `ALIVE` record is included in subsequent ACK and gossip messages.

This is the mechanism that allows a falsely suspected live node to refute suspicion.

## 9. Local-only membership metadata

The following fields are not serialized:

- `suspected_at: monotonic timestamp | None`
- `dead_at: monotonic timestamp | None`

A `MembershipTable` owns these timers separately from `ClusterMember` so wire state remains deterministic and portable.

When a member changes to `ALIVE`, suspicion/dead timers are cleared.

When a member first changes to `SUSPECT`, `suspected_at` is recorded.

When suspicion exceeds the configured timeout, the member becomes `DEAD` and `dead_at` is recorded.

A `DEAD` member is retained for `CLUSTER_DEAD_RETENTION_SECONDS` as a tombstone. After retention expires it may be purged.

## 10. Failure detection: SWIM-lite

Recommended defaults:

```text
CLUSTER_PROBE_INTERVAL_SECONDS=1.0
CLUSTER_PING_TIMEOUT_SECONDS=0.25
CLUSTER_INDIRECT_TIMEOUT_SECONDS=0.50
CLUSTER_INDIRECT_PROBE_COUNT=2
CLUSTER_SUSPICION_TIMEOUT_SECONDS=3.0
CLUSTER_DEAD_RETENTION_SECONDS=30.0
```

Each detector iteration:

1. Advance expired suspicions to `DEAD` and purge expired tombstones.
2. Choose one peer from `ALIVE` or `SUSPECT`, excluding self.
3. Send one direct `PING` with the local membership snapshot.
4. If direct ACK succeeds, merge its gossip and leave/restore the target according to the merge result.
5. If direct probe fails, choose up to `CLUSTER_INDIRECT_PROBE_COUNT` `ALIVE` helpers excluding self and target.
6. Send `PING_REQ(target)` to helpers concurrently.
7. If any helper returns `ACK(success=true)`, treat the target as reachable and merge returned gossip.
8. If all indirect probes fail, mark the target `SUSPECT` if it is not already suspect.
9. A later probe or gossip can refute suspicion through a higher incarnation.
10. If no refutation arrives before the suspicion timeout, mark the target `DEAD`.

Probe candidates include `SUSPECT` nodes during their suspicion window. This is deliberate: it gives a live suspected target a direct opportunity to receive the suspicion gossip, increment its incarnation, and return a newer `ALIVE` record even in a two-node cluster.

Failure-detector control probes do not use task retry or task circuit breakers. Indirect probing is the failure detector's resilience mechanism.

## 11. Gossip dissemination

Recommended default:

```text
CLUSTER_GOSSIP_INTERVAL_SECONDS=1.0
```

Each gossip iteration selects one `ALIVE` peer excluding self and sends the full membership snapshot.

The full table is appropriate for the intended three-node development cluster. Delta dissemination, retransmission counters, and Lifeguard-style adaptive suspicion are out of scope.

Gossip failures are logged at debug/warning level and do not directly mark a node suspect. Failure status is owned by the failure detector.

## 12. Consistent hashing

The ring uses SHA-256 and 64 virtual nodes per physical member by default:

```text
CLUSTER_VIRTUAL_NODES=64
```

For each `ALIVE` physical member with id `node-1`, create positions from:

```text
SHA256("node-1#0")
...
SHA256("node-1#63")
```

Only `ALIVE` members participate in the ring. `SUSPECT` and `DEAD` members are removed from new ownership immediately.

The ring API provides:

- `rebuild(members: Iterable[ClusterMember]) -> None`
- `owner(key: str) -> ClusterMember`
- `candidates(key: str) -> list[ClusterMember]`

`candidates()` walks clockwise around virtual-node positions and returns unique physical members in deterministic failover order.

If no `ALIVE` members exist, `owner()` and `candidates()` raise `NoRouteError`.

Ring positions depend only on `node_id` and virtual-node index, not host or port. Nodes with identical alive membership therefore build identical rings.

## 13. Cluster routing

### 13.1 Client API

Extend both client methods with an optional keyword-only routing key:

```python
await client.request(task_name, payload, routing_key="customer-123")
await client.request_connected(task_name, payload, routing_key="customer-123")
```

Omitting the routing key keeps Phase-2 behavior.

### 13.2 Ingress task flow

For normal `REQUEST` traffic:

1. Decode task request.
2. Apply the public token-bucket rate limiter.
3. Create one request deadline using `REQUEST_TIMEOUT_SECONDS`.
4. If clustering is disabled or routing key is empty, execute locally.
5. Otherwise ask `ClusterRouter` to execute using consistent-hash candidates.

### 13.3 Local execution flow

Backpressure moves to a local-execution helper rather than wrapping the entire request path.

This matters because a remotely routed request should not consume a local CPU/admission slot while merely waiting on network I/O.

Local execution:

1. Try node backpressure admission.
2. If full, raise/return `OVERLOADED`.
3. Execute through the Phase-2 `TaskExecutor` using the shared deadline.
4. Release admission in `finally`.

This same helper is used for ordinary local requests and forwarded requests.

### 13.4 Forwarded request flow

`FORWARDED_REQUEST`:

- bypasses the public token-bucket limiter because the original ingress node already rate-limited the user request,
- always executes locally,
- still enforces local backpressure,
- constructs a deadline from `remaining_timeout_ms`,
- never consults the hash ring,
- returns ordinary task `RESPONSE` or `ERROR`.

Cluster-control traffic also bypasses the public task limiter and execution backpressure.

## 14. Peer client and resilience boundaries

`PeerClient` performs one-shot framed TCP exchanges to cluster peers.

### 14.1 Task forwarding

Remote task forwarding uses:

- the original routing candidate member,
- the same logical correlation id across transport retry attempts; the payload may be rebuilt only to reduce `remaining_timeout_ms` to the current shared deadline budget,
- the request's remaining deadline budget,
- Phase-2 full-jitter retry,
- a per-peer circuit breaker keyed by `node_id`.

### 14.2 Transport-only retry

Retry applies only to transport-level failures such as:

- `ConnectionRefusedError`
- `ConnectionResetError`
- timeout while opening/writing/reading the peer connection
- other connection-level `OSError`

Remote application responses are not retried by the retry helper.

The configured Phase-2 policy remains:

- max attempts: 3
- base delay: 0.05 seconds
- max delay: 1.0 second
- full jitter

The same deadline is shared across attempts. Retry never resets a new five-second budget.

### 14.3 Circuit-breaker boundary

The circuit breaker wraps only the raw transport exchange. A peer that returns `INVALID_REQUEST`, `UNKNOWN_TASK`, or another structured application response is demonstrably reachable and must not increment circuit-breaker failure count.

Each remote physical node has its own breaker.

Control-plane `PING`, `PING_REQ`, `GOSSIP`, and `JOIN_REQUEST` do not use the task circuit breaker.

## 15. Failover semantics

`ClusterRouter` evaluates `candidates(routing_key)` in deterministic order.

- If the candidate is local, execute locally.
- If remote, forward through `PeerClient`.
- Transport failure or open circuit: try the next candidate while deadline remains.
- `OVERLOADED`: try the next candidate.
- `RATE_LIMITED`: may try the next candidate for forward compatibility, although Phase-3 forwarded traffic itself bypasses the public limiter.
- `INVALID_REQUEST`: return immediately; do not fail over.
- `UNKNOWN_TASK`: return immediately; do not fail over.
- `INTERNAL_ERROR`: return immediately; do not replay.
- `TIMEOUT`: return immediately; do not replay because execution may already have started.

If no `ALIVE` candidate exists, return `NO_ROUTE`.

If candidates exist but every usable candidate fails with transport/circuit/overload-type conditions, return `PEER_UNAVAILABLE`.

## 16. Delivery semantics

Phase 3 does not claim exactly-once execution.

Remote transport retry can produce duplicate execution if a peer finishes a task but the response is lost before the origin receives it. Phase-3 built-in routed workloads are pure/stateless, so replay is acceptable.

The documented guarantee is:

> best-effort keyed routing with bounded transport retries and failover for stateless/idempotent work.

Persistent deduplication/idempotency records are deferred to a later state/recovery phase.

## 17. Diagnostic task for routing proof

Add a lightweight async built-in task named:

```text
cluster.whoami
```

It returns:

```json
{"node_id":"node-1"}
```

The task is registered per node using its configured `node_id` and defaults to asynchronous execution classification.

Its purpose is deterministic integration/smoke verification that a request received by one node actually executed on the consistent-hash owner.

It is not a health-check protocol and does not replace `PING`.

## 18. Component boundaries

Create `src/distsys/cluster/`.

### `member.py`

Owns:

- `MemberStatus`
- immutable `ClusterMember`
- immutable `SeedAddress`
- seed parsing
- fresh incarnation creation

It does not perform networking or maintain timers.

### `membership.py`

Owns:

- membership records
- incarnation merge rules
- self-refutation
- suspicion and dead timers
- dead tombstone retention
- snapshots and peer selection inputs
- monotonically increasing change version

It does not send network messages.

### `codec.py`

Owns conversion between domain membership objects and Protobuf plus encode/decode for:

- join
- ping
- ack
- ping request
- gossip
- forwarded tasks

It does not open sockets.

### `consistent_hash.py`

Owns ring construction and deterministic `owner()` / `candidates()` selection.

It depends only on domain members.

### `peer_client.py`

Owns one-shot peer network exchanges, correlation validation, forwarding, per-peer task circuit breakers, and transport-only task retries.

It exposes separate control operations that do not use task retry/circuit breakers.

### `failure_detector.py`

Owns direct/indirect probe scheduling and `SUSPECT` transitions. It delegates state storage to `MembershipTable` and network I/O to `PeerClient`.

### `gossip.py`

Owns periodic best-effort dissemination to one alive peer.

### `cluster_router.py`

Owns keyed task ownership and candidate failover. It depends on the current ring, local task execution callback, and `PeerClient`.

### `service.py`

Owns cluster lifecycle and coordination:

- local member creation after server bind,
- seed bootstrap,
- membership table,
- consistent-hash rebuild after membership changes,
- failure-detector lifecycle,
- gossip lifecycle,
- control-message dispatch,
- graceful stop of background tasks.

`DistributedNode` delegates cluster-control handling to this service and keeps responsibility for the TCP server and task responses.

## 19. Membership-to-ring synchronization

`MembershipTable` maintains a change version that increments whenever a stored member record or tombstone state changes.

`ClusterService` rebuilds the consistent hash ring after any merge/transition that changes membership version.

Ring rebuilds are cheap for three nodes and 64 virtual nodes, so Phase 3 does not introduce incremental ring mutation complexity.

## 20. Node lifecycle

Cluster-enabled node startup:

1. Start `TaskExecutor`.
2. Bind the TCP server.
3. Build local member using `bound_port`.
4. Create `ClusterService` and membership table.
5. Bootstrap through seeds when configured.
6. Start detector and gossip loops.
7. Report node ready.

If bootstrap fails:

1. Stop cluster service/background work.
2. Close server.
3. Close executor.
4. Re-raise startup failure.

Shutdown order:

1. Stop failure detector and gossip.
2. Close TCP listener.
3. Close active writers/handlers.
4. Close `TaskExecutor` / process pool.

This prevents background cluster tasks from opening new peer connections while the server is shutting down.

## 21. Control-message dispatch

`DistributedNode.handle_message()` classifies messages before task rate limiting:

```text
JOIN_REQUEST / PING / PING_REQ / GOSSIP
        |
        +--> ClusterService.handle_control()

FORWARDED_REQUEST
        |
        +--> local task execution only

REQUEST
        |
        +--> public rate limiter
             |
             +--> local execution OR ClusterRouter
```

When clustering is disabled, cluster-control and forwarded message types return structured `INVALID_REQUEST` errors rather than changing node state.

## 22. Configuration

Extend `Settings` with:

```text
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

Validation rules:

- virtual nodes >= 1
- probe interval > 0
- ping timeout > 0
- indirect timeout > 0
- indirect probe count >= 0
- suspicion timeout > 0
- dead retention > suspicion timeout
- gossip interval > 0
- each seed parses as valid host:port

`CLUSTER_SEEDS` is comma separated. Whitespace around entries is stripped. Empty overall value means no seeds.

## 23. Production file map

### New files

```text
src/distsys/cluster/
├── __init__.py
├── member.py
├── membership.py
├── codec.py
├── consistent_hash.py
├── peer_client.py
├── failure_detector.py
├── gossip.py
├── cluster_router.py
└── service.py
```

```text
scripts/phase3_smoke.py
scripts/run_phase3_cluster.sh
```

### Modified files

```text
proto/messages.proto
src/distsys/proto/messages_pb2.py          generated
src/distsys/proto/messages_pb2.pyi         generated
src/distsys/protocol/message.py
src/distsys/protocol/codec.py
src/distsys/client.py
src/distsys/node.py
src/distsys/utils/config.py
.env.example
Makefile
README.md
docs/PHASES.md
```

Phase-2 resilience modules are reused, not duplicated.

## 24. Test map

### Unit tests

```text
tests/unit/test_member.py
tests/unit/test_membership.py
tests/unit/test_cluster_codec.py
tests/unit/test_consistent_hash.py
tests/unit/test_peer_client.py
tests/unit/test_failure_detector.py
tests/unit/test_gossip.py
tests/unit/test_cluster_router.py
tests/unit/test_cluster_config.py
```

Required unit behaviors:

- stale incarnation ignored,
- higher incarnation accepted,
- equal-incarnation severity ordering,
- self-suspicion/self-dead refutation increments incarnation,
- tombstone retention blocks stale resurrection,
- tombstone purge after retention,
- seed parsing/validation,
- Protobuf round trips for all control messages,
- deterministic ring ownership,
- identical rings for identical membership,
- unique candidate order,
- only affected keys move after member removal,
- direct probe success,
- indirect probe after direct failure,
- successful indirect probe avoids suspicion,
- failed direct+indirect marks suspect,
- suspicion expiry marks dead,
- transport failures retry for forwarded tasks,
- structured application failures do not retry or trip breaker,
- open peer circuit skips transport call,
- local owner executes locally,
- remote owner forwards,
- overload transport candidate fails over,
- invalid/unknown application failures do not fail over,
- exhausted candidates raise peer unavailable.

### Integration tests

```text
tests/integration/test_cluster_join.py
tests/integration/test_gossip_convergence.py
tests/integration/test_failure_detection.py
tests/integration/test_distributed_routing.py
tests/integration/test_routing_failover.py
tests/integration/test_node_rejoin.py
tests/integration/test_cluster_control_under_load.py
```

Every network integration test uses pytest `unused_tcp_port_factory`; no new integration test uses `port=0` directly.

## 25. Integration acceptance scenarios

### 25.1 Join and convergence

Start node-0 seed, then node-1 and node-2 using node-0 as seed. Eventually each membership table contains all three nodes as `ALIVE`.

### 25.2 Deterministic routed execution

Calculate the expected owner for a routing key. Send `cluster.whoami` to a different ingress node using that routing key. The returned `node_id` must equal the calculated owner.

### 25.3 Failure detection

Stop the current owner. Remaining nodes must transition it `ALIVE -> SUSPECT -> DEAD` within configured test timings and remove it from the ring as soon as it becomes `SUSPECT`.

### 25.4 Failover

While the original owner is unavailable, send the same routing key. The next healthy consistent-hash candidate must execute the idempotent `cluster.whoami` task without client topology knowledge.

### 25.5 Rejoin

Restart the failed node with the same `node_id`, same address, and a newer incarnation. Membership converges to `ALIVE`, the ring includes it again, and stale tombstones do not override it.

### 25.6 Control plane under task load

Generate enough ordinary task traffic to consume/reject public rate-limit capacity while sending control probes. PING/ACK and gossip must remain functional because they bypass the task token bucket.

## 26. Smoke scripts

### `run_phase3_cluster.sh`

Starts three local nodes with:

- node-0 :18000 seedless,
- node-1 :18001 seeded to node-0,
- node-2 :18002 seeded to node-0,
- `CPU_WORKERS=1`,
- trap-based cleanup for all child PIDs,
- separate log files under a temporary/log directory.

It must fail if any required port is already occupied rather than silently attaching to an old process.

### `phase3_smoke.py`

The smoke workflow verifies:

1. all three endpoints respond to direct cluster probes,
2. membership snapshots converge to three `ALIVE` members,
3. ring calculations agree across snapshots,
4. multiple keys distribute across at least two physical nodes,
5. `cluster.whoami` proves remote execution on calculated owners,
6. after manually/optionally stopping one node, remaining nodes detect failure and route around it,
7. after restart with a newer incarnation, membership reconverges.

The automated default smoke may stop/restart only processes it launched itself. It must never kill an arbitrary PID discovered on the machine.

## 27. Logging

Add structured cluster events using the existing logging approach. At minimum:

```text
cluster_joined
membership_changed
member_suspect
member_dead
member_refuted
cluster_gossip_sent
cluster_gossip_failed
peer_forward
peer_forward_failed
route_failover
```

Do not log every successful PING at INFO in the normal profile; successful probe chatter belongs at DEBUG to avoid overwhelming development logs.

## 28. Error behavior

- Malformed cluster protobuf: structured `INVALID_REQUEST` where a response is possible; log protocol detail server-side.
- Cluster control received while clustering disabled: `INVALID_REQUEST`.
- No alive routing candidate: `NO_ROUTE`.
- All candidates unusable from transport/open-circuit/overload conditions: `PEER_UNAVAILABLE`.
- Remote `INVALID_REQUEST` / `UNKNOWN_TASK`: preserve code/message to the client.
- Remote `INTERNAL_ERROR` / `TIMEOUT`: preserve and do not replay.
- Forwarded request with zero timeout budget: `TIMEOUT` without executing.
- Forwarded request with invalid/empty origin id: `INVALID_REQUEST`.
- Peer response correlation mismatch: transport/protocol failure and eligible for task retry within deadline.

## 29. Concurrency and shutdown safety

Membership mutations are serialized with an `asyncio.Lock` or otherwise guaranteed to execute atomically on the event loop. Snapshots return immutable copies so callers do not mutate table state.

Background detector/gossip tasks are explicitly stored, cancelled on stop, and awaited with `return_exceptions=True`.

Peer control operations use one-shot connections; Phase 3 does not add multiplexed peer sessions.

The existing public client persistent connection remains sequential.

## 30. Non-goals

Phase 3 explicitly excludes:

- replicated application data,
- CRDTs and vector clocks,
- leader election or consensus,
- etcd/Consul/ZooKeeper discovery,
- exactly-once execution,
- durable membership persistence,
- authentication, TLS, or mTLS,
- Prometheus/Grafana,
- chaos framework,
- Docker multi-node production topology,
- Kubernetes and Terraform.

These are later phases.

## 31. Phase-3 exit criteria

Phase 3 is complete only when all of the following are demonstrated:

- 3-node static-seed bootstrap works.
- Membership gossip converges.
- Direct probing works.
- Indirect probing works.
- `ALIVE -> SUSPECT -> DEAD` works.
- Self-refutation with higher incarnation works.
- Dead tombstone retention prevents stale resurrection.
- Node rejoin with newer incarnation works.
- SHA-256 consistent hashing is deterministic.
- 64 virtual nodes are used by default.
- `SUSPECT` and `DEAD` nodes are excluded from ownership.
- Optional routing key preserves local Phase-2 compatibility when absent.
- Local keyed execution works.
- Remote single-hop forwarding works.
- Forwarded requests never reroute.
- Shared timeout budget is enforced across remote forwarding.
- Transport-only full-jitter retry is used for peer task calls.
- Per-peer circuit breakers are used for task forwarding only.
- Candidate failover works for transport/open-circuit/overload conditions.
- Deterministic application errors are not retried/failover replayed.
- Cluster control bypasses the public task limiter.
- All Phase-1 tests pass.
- All Phase-2 tests pass.
- All Phase-3 tests pass.
- Ruff passes.
- Black passes.
- mypy passes.
- Three-node laptop smoke succeeds.
- Documentation clearly states best-effort/idempotent delivery semantics rather than claiming exactly once.

Only after those gates are green should `v0.3.0` be created.
