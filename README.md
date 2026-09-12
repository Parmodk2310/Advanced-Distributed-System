# Advanced Distributed System — Phase 2

Phase 2 extends the reliable Phase-1 TCP/Protobuf foundation with bounded compute execution and reusable resilience primitives while deliberately staying single-node.

## What Phase 2 proves

- Phase-1 framed TCP + Protobuf protocol remains compatible.
- Explicit task classification separates asyncio work from CPU work.
- CPU-bound `hash`, `sort`, and `aggregate` tasks run through `ProcessPoolExecutor`.
- Conservative default: `CPU_WORKERS=2`.
- Deterministic bounded admission prevents unbounded in-flight work.
- The CPU worker pool also bounds submitted process work, including jobs that outlive a client deadline.
- Token-bucket rate limiting returns structured `RATE_LIMITED` errors.
- Saturation returns structured `OVERLOADED` errors.
- A single monotonic request deadline returns structured `TIMEOUT` errors.
- Retry uses exponential backoff with full jitter and is deadline-aware.
- Circuit breaker implements CLOSED -> OPEN -> HALF_OPEN -> CLOSED.
- Retry and circuit breaker are libraries only in Phase 2; they are intentionally not wrapped around local CPU work.
- CPU integration tests verify the asyncio event loop remains responsive.

Not included yet: gossip, consistent hashing, peer routing, CRDTs, etcd, TLS/mTLS, Prometheus/Grafana, Docker cluster, Kubernetes, or Terraform.

## Architecture

```text
TCP request
    |
    v
frame + protobuf decode
    |
    v
TokenBucketRateLimiter
    |
    v
BackpressureController
    |
    v
Deadline
    |
    v
TaskExecutor
    +---- ASYNC ----> TaskRouter / asyncio handler
    |
    +---- CPU ------> WorkerPool -> ProcessPoolExecutor(max_workers=2)
    |
    v
structured Protobuf response
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

If `proto/messages.proto` changes:

```bash
make proto
```

This regenerates both `messages_pb2.py` and `messages_pb2.pyi`.

## Recommended laptop development profile

```bash
export NODE_ID=node-0
export NODE_HOST=127.0.0.1
export NODE_PORT=18000
export LOG_LEVEL=INFO

export CPU_WORKERS=2
export CPU_QUEUE_CAPACITY=200
export REQUEST_TIMEOUT_SECONDS=5
export RATE_LIMIT_RPS=500
export RATE_LIMIT_BURST=100
```

Port `18000` is only a development recommendation when `8000` conflicts with another local process.

## Run

Terminal 1:

```bash
python -m distsys.main
```

Terminal 2:

```bash
python scripts/phase2_smoke.py --port 18000
```

Or call individual tasks:

```python
import asyncio
from distsys.client import DistributedClient


async def main():
    client = DistributedClient(host="127.0.0.1", port=18000)
    print(await client.request("echo", {"message": "hello"}))
    print(await client.request("hash", {"data": "hello", "rounds": 50000}))
    print(await client.request("sort", {"values": [5, 1, 4, 2, 3]}))
    print(await client.request("aggregate", {"values": [1, 2, 3, 4]}))


asyncio.run(main())
```

## Tests and quality

```bash
make quality
```

The Phase-2 suite includes unit coverage for classification, compute tasks, worker pool, executor, backpressure, rate limiting, deadlines, retry, and circuit breaker plus integration coverage for CPU execution, overload, timeout behavior, and event-loop responsiveness.

## Correctness benchmark

The default Phase-2 rate limiter is intentionally conservative, so a fast local smoke client can be rate-limited. For a protocol-correctness run, start a dedicated benchmark node with a high temporary rate limit:

```bash
export NODE_PORT=18000
export LOG_LEVEL=WARNING
export RATE_LIMIT_RPS=1000000
export RATE_LIMIT_BURST=10000
python -m distsys.main
```

Then in a second terminal:

```bash
python scripts/smoke_test.py \
  --host 127.0.0.1 \
  --port 18000 \
  --requests 10000 \
  --mode persistent
```

Return to the normal `RATE_LIMIT_RPS=500` and `RATE_LIMIT_BURST=100` development defaults afterward. Treat this as a correctness test, not a published performance benchmark. Formal concurrent throughput/latency benchmarking belongs to Phase 6.

## Known Phase-2 limitation

A request deadline can stop waiting for CPU work, but `ProcessPoolExecutor` cannot safely kill a Python function that is already running. The client receives a structured `TIMEOUT`; the underlying CPU job may finish later. Its bounded worker-pool slot remains reserved until actual completion, which prevents timed-out requests from building an unbounded hidden queue. Hard worker preemption is intentionally out of scope for Phase 2.

## Phase-2 exit criteria

- All Phase-1 tests remain green.
- Built-in CPU tasks execute through the process pool.
- CPU work does not block echo responsiveness.
- Overload/rate-limit/deadline failures are structured protocol errors.
- Retry and circuit-breaker state behavior are fully unit-tested.
- `make quality` passes.

See `docs/superpowers/specs/2026-09-12-phase2-compute-resilience-design.md` for the design and `docs/superpowers/plans/2026-09-12-phase2-compute-resilience.md` for the implementation plan.
