# Phase 2 Compute & Resilience Design

> **Document status:** Historical design record. Phase 2 is implemented and verified. This file preserves the original design decisions; see the [current architecture](../architecture/phase2-compute-resilience.md) and [verification record](../verification/phase2.md).

## Goal

Extend the Phase-1 single-node TCP/Protobuf system with bounded execution, CPU-process isolation, rate limiting, request deadlines, and reusable retry/circuit-breaker primitives without adding multi-node behavior.

## Constraints

- Python 3.12 compatible.
- One local node for Phase 2.
- `ProcessPoolExecutor(max_workers=2)` by default.
- Bounded in-flight admission, default capacity 200.
- Request deadline default 5 seconds.
- Rate limiter default 500 requests/sec with burst 100.
- Retry and circuit breaker are implemented and unit-tested but are not wrapped around local CPU execution.
- No gossip, consistent hashing, etcd, CRDTs, TLS/mTLS, Prometheus/Grafana, Docker cluster, Kubernetes, or Terraform in this phase.
- Existing Phase-1 echo/protocol behavior must remain compatible.

## Architecture

The node decodes a request, applies a token-bucket rate limiter, acquires bounded backpressure admission, creates one request deadline, and delegates execution to `TaskExecutor`. `TaskExecutor` uses explicit task classification: asynchronous tasks execute through `TaskRouter`, while CPU tasks execute through a two-process `WorkerPool`. CPU work never runs directly on the asyncio event loop.

Retry and circuit-breaker primitives are independent resilience libraries for Phase-3 remote peer calls. They are not used to retry local computation in Phase 2.

## Request Flow

```text
TCP request
  -> frame/protobuf decode
  -> rate limiter
  -> bounded backpressure
  -> request deadline
  -> TaskExecutor
       -> ASYNC -> TaskRouter -> asyncio handler
       -> CPU   -> WorkerPool -> ProcessPoolExecutor(max_workers=2)
  -> structured TaskResponse
```

## Compute Components

### `classification.py`

Defines `ExecutionClass` (`ASYNC`, `CPU`) and `TaskClassifier`. Unknown names default to `ASYNC`, allowing `TaskRouter` to remain the source of truth for unknown-task errors.

Default mapping:

- `echo` -> ASYNC
- `hash` -> CPU
- `sort` -> CPU
- `aggregate` -> CPU

### `tasks.py`

Provides:

- `echo_task`: asynchronous identity task.
- `hash_task`: repeated SHA-256 workload with bounded `rounds`.
- `sort_task`: validates and sorts numeric JSON arrays.
- `aggregate_task`: count/sum/min/max/mean for a non-empty numeric array.

Invalid task payloads raise `TaskValidationError`.

### `worker_pool.py`

Wraps `ProcessPoolExecutor` with explicit lifecycle and a bounded pending-submission limiter. It rejects new work after close, rejects CPU submissions when the pending capacity is full, and converts broken-pool failures into typed worker-pool errors. Process creation is lazy as provided by the standard executor. A pending slot is released only when the underlying process future actually completes, so cancellation or a request deadline cannot silently create an unbounded hidden process backlog.

### `executor.py`

Single execution facade. It resolves the task classification, runs asynchronous tasks through `TaskRouter`, runs CPU tasks through `WorkerPool`, and enforces the same `Deadline` around either execution path.

## Resilience Components

### `backpressure.py`

Deterministic non-waiting admission control. `try_acquire()` succeeds only while `in_flight < capacity`; callers release in a `finally` block.

### `rate_limiter.py`

Token-bucket limiter using `time.monotonic()`. Supports an injected clock for deterministic tests.

### `deadline.py`

Represents one monotonic request budget. `Deadline.after(seconds)` establishes the absolute deadline; `remaining()`, `expired()`, and `run(awaitable)` consume the same budget. A timed-out CPU request stops waiting and returns `TIMEOUT`, but Python's process pool cannot safely preempt an already-running function. The worker-pool pending slot therefore remains occupied until that process work really finishes.

### `retry.py`

Asynchronous retry helper with exponential backoff and full jitter: random sleep in `[0, min(max_delay, base_delay * 2**retry_index)]`. The helper accepts an optional `Deadline` and does not retry non-retryable exceptions.

### `circuit_breaker.py`

Async-safe CLOSED/OPEN/HALF_OPEN state machine. Consecutive failures open the breaker; after the recovery timeout, a bounded number of half-open probes are allowed. Success closes/reset; failure reopens.

## Failure Mapping

- Unknown task -> `UNKNOWN_TASK`.
- Invalid task/protobuf payload -> `INVALID_REQUEST`.
- Request deadline exceeded -> `TIMEOUT`.
- Backpressure capacity exhausted -> `OVERLOADED`.
- Token bucket rejects -> `RATE_LIMITED`.
- Unexpected task/worker failure -> `INTERNAL_ERROR` with details logged server-side only.

The protobuf `ErrorCode` enum gains `OVERLOADED = 5` and `RATE_LIMITED = 6`.

## Configuration

New defaults:

- `CPU_WORKERS=2`
- `CPU_QUEUE_CAPACITY=200`
- `RATE_LIMIT_RPS=500`
- `RATE_LIMIT_BURST=100`
- `REQUEST_TIMEOUT_SECONDS=5`
- `RETRY_MAX_ATTEMPTS=3`
- `RETRY_BASE_DELAY_SECONDS=0.05`
- `RETRY_MAX_DELAY_SECONDS=1.0`
- `CIRCUIT_BREAKER_FAILURE_THRESHOLD=5`
- `CIRCUIT_BREAKER_RECOVERY_SECONDS=10`

## Testing

Phase 2 adds unit tests for classification, compute tasks, worker pool, executor, backpressure, rate limiter, deadline, retry, and circuit breaker. Integration tests cover CPU pipeline execution, overload/rate-limit responses, deadline behavior, and event-loop responsiveness while CPU work is running. All Phase-1 tests remain green.

## Exit Criteria

- Echo remains compatible.
- CPU tasks execute in the process pool with default 2 workers.
- Event loop remains responsive while a CPU task runs.
- Admission is bounded and overload is a structured response.
- Rate limiting produces a structured response.
- Request deadlines produce `TIMEOUT` without crashing the node.
- Retry uses full jitter and respects max attempts/deadline.
- Circuit breaker transitions are fully unit-tested.
- `make quality` passes.
