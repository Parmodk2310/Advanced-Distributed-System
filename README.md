# Advanced Distributed System — Phase 3

Phase 3 extends the verified Phase-2 async TCP/Protobuf runtime into a small decentralized cluster with static-seed bootstrap, gossip membership, SWIM-lite failure detection, deterministic SHA-256 consistent hashing, single-hop task forwarding, and bounded failover for stateless/idempotent workloads.

## What Phase 3 proves

- Three nodes can bootstrap through static seed addresses without a permanent leader.
- Membership converges through gossip and retains incarnation-aware `ALIVE`, `SUSPECT`, and `DEAD` state.
- Direct PING plus indirect `PING_REQ` probes distinguish peer failure from one-sided reachability problems.
- False suspicion can be refuted by a live node with a higher incarnation.
- Dead-member tombstones prevent same-incarnation stale resurrection.
- Only `ALIVE` members participate in new consistent-hash ownership.
- SHA-256 with 64 virtual nodes produces deterministic ownership and deterministic failover candidate ordering.
- A client may connect to one node while a keyed task executes on another node.
- Forwarded requests are executed locally at the receiver and are never routed again.
- Phase-2 full-jitter retry and per-peer circuit breakers are used only for remote task transport.
- Cluster-control traffic bypasses the public task token bucket and local execution admission.
- Standalone Phase-2 behavior remains the default when `CLUSTER_ENABLED=false`.

Phase 3 intentionally does **not** implement consensus, exactly-once execution, replicated application state, CRDTs, durable membership, etcd, TLS/mTLS, Prometheus/Grafana, Kubernetes, or Terraform.

## Delivery semantics

Phase 3 provides **best-effort keyed routing with bounded transport retries and failover for stateless/idempotent work**.

It does not claim exactly-once execution. A remote task can complete while its TCP response is lost, so a transport retry can execute a pure/idempotent task more than once. Persistent request deduplication belongs to a later state/recovery phase.

## Architecture

```text
                         CLIENT
                           |
                           v
                    +-------------+
                    |   node-0    |
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
                              shared Deadline
                                     |
                              Retry + Jitter
                                     |
                              CircuitBreaker
                                     |
                                     v
                              +-------------+
                              |   node-1    |
                              |   :18001    |
                              +-------------+

Control plane on the same framed TCP endpoint:

node-0 <---- JOIN / PING / PING_REQ / GOSSIP ----> node-1
   ^                                                ^
   |                                                |
   +------------------------------ control --------> node-2
                                                    :18002
```

## Cluster components

```text
src/distsys/cluster/
├── member.py              # immutable member/seed domain types
├── membership.py          # merge rules, self-refutation, tombstones
├── codec.py               # cluster Protobuf codecs
├── consistent_hash.py     # SHA-256 ring + failover candidates
├── peer_client.py         # peer TCP, retry, per-peer circuit breaker
├── failure_detector.py    # SWIM-lite direct/indirect probing
├── gossip.py              # best-effort membership dissemination
├── cluster_router.py      # keyed local/remote routing + failover
└── service.py             # bootstrap, lifecycle, control dispatch
```

## Protocol additions

Phase 3 preserves the existing numeric values:

```text
REQUEST=1
RESPONSE=2
ERROR=3
HEARTBEAT=4
```

and adds:

```text
JOIN_REQUEST=5
JOIN_RESPONSE=6
PING=7
ACK=8
PING_REQ=9
GOSSIP=10
FORWARDED_REQUEST=11
```

Existing error codes 0–6 are unchanged. Phase 3 adds:

```text
NO_ROUTE=7
PEER_UNAVAILABLE=8
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

After changing `proto/messages.proto`:

```bash
make proto
```

## Standalone compatibility

Cluster mode is disabled by default:

```bash
export NODE_ID=node-0
export NODE_HOST=127.0.0.1
export NODE_PORT=18000
export CLUSTER_ENABLED=false
python -m distsys.main
```

An unkeyed request still uses the Phase-2 local path:

```python
await client.request("echo", {"message": "local"})
```

## Recommended three-node laptop profile

Use one CPU worker per node when all three local nodes are running:

```text
node-0  127.0.0.1:18000
node-1  127.0.0.1:18001
node-2  127.0.0.1:18002

CPU_WORKERS=1
CPU_QUEUE_CAPACITY=100
RATE_LIMIT_RPS=500
RATE_LIMIT_BURST=100
CLUSTER_VIRTUAL_NODES=64
```

The default Phase-3 timing profile is:

```text
CLUSTER_PROBE_INTERVAL_SECONDS=1.0
CLUSTER_PING_TIMEOUT_SECONDS=0.25
CLUSTER_INDIRECT_TIMEOUT_SECONDS=0.50
CLUSTER_INDIRECT_PROBE_COUNT=2
CLUSTER_SUSPICION_TIMEOUT_SECONDS=3.0
CLUSTER_DEAD_RETENTION_SECONDS=30.0
CLUSTER_GOSSIP_INTERVAL_SECONDS=1.0
```

## Run the local cluster

The runner refuses to start if ports 18000, 18001, or 18002 are already occupied and only terminates child processes it created.

```bash
make phase3-cluster
```

Equivalent command:

```bash
bash scripts/run_phase3_cluster.sh
```

Logs are written to `.phase3-logs/` by default.

## Inspect the running cluster

In another terminal:

```bash
source .venv/bin/activate
make phase3-smoke
```

The default smoke verifies:

- all three endpoints answer cluster PING,
- every returned membership snapshot converges to three `ALIVE` members,
- SHA-256 ring ownership is deterministic,
- a routing key owned by a remote node executes there via `cluster.whoami`,
- 100 sample keys map across at least two physical nodes.

For a fully managed failure/failover/rejoin demonstration, ensure the three Phase-3 ports are free and run:

```bash
python scripts/phase3_smoke.py \
  --host 127.0.0.1 \
  --ports 18000 18001 18002 \
  --managed-command 'bash scripts/run_phase3_cluster.sh'
```

Managed mode only sends signals to the runner/processes it launched itself.

## Keyed routing example

```python
import asyncio

from distsys.client import DistributedClient


async def main() -> None:
    client = DistributedClient(host="127.0.0.1", port=18000)

    local = await client.request("echo", {"message": "unkeyed"})
    routed = await client.request(
        "cluster.whoami",
        {},
        routing_key="customer-123",
    )

    print(local)
    print(routed)


asyncio.run(main())
```

`cluster.whoami` is a diagnostic task used to prove where a keyed request actually executed.

## Request flow

```text
REQUEST without routing_key
    -> public rate limiter
    -> local backpressure
    -> TaskExecutor

REQUEST with routing_key
    -> public rate limiter
    -> shared Deadline
    -> ConsistentHashRing.candidates(key)
       -> local candidate: local backpressure -> TaskExecutor
       -> remote candidate: PeerClient -> retry/circuit breaker -> FORWARDED_REQUEST

FORWARDED_REQUEST
    -> bypass public token bucket
    -> local deadline from remaining_timeout_ms
    -> local backpressure
    -> TaskExecutor
    -> never route again

JOIN/PING/PING_REQ/GOSSIP
    -> ClusterService control path
    -> bypass public task limiter/backpressure
```

## Failover behavior

Failover to the next consistent-hash candidate is allowed for:

```text
transport failure
open peer circuit
OVERLOADED
RATE_LIMITED (forward-compatible handling)
```

The request is **not** replayed to another candidate for:

```text
INVALID_REQUEST
UNKNOWN_TASK
INTERNAL_ERROR
TIMEOUT
```

The latter two can represent work that already started, so Phase 3 avoids pretending they are safe to replay.

## Tests and quality

```bash
make quality
```

The Phase-3 test suite covers membership merge rules, self-refutation, tombstones, cluster codecs, consistent hashing, peer retry/circuit-breaker boundaries, routing/failover, failure detection, gossip, bootstrap/control handling, three-node convergence, failure detection, node rejoin, and control-plane isolation under task rate limiting.

## Release gate

Create `v0.3.0` only after:

```text
all Phase-1 tests pass
all Phase-2 tests pass
all Phase-3 tests pass
Ruff passes
Black passes
mypy passes
three-node smoke passes
managed failure/failover/rejoin smoke passes
ports 18000/18001/18002 are free after shutdown
```

See:

- `docs/superpowers/specs/2026-09-13-phase3-distributed-cluster-design.md`
- `docs/superpowers/plans/2026-09-13-phase3-distributed-cluster.md`
- `docs/PHASE3_FILE_MANIFEST.md`
- `docs/PHASE3_VERIFICATION.md`
