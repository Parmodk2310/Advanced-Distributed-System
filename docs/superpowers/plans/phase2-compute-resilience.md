# Phase 2 Compute & Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded CPU execution and resilience primitives to the Phase-1 node while preserving protocol compatibility and event-loop responsiveness.

**Architecture:** Requests pass through rate limiting, bounded admission, and one monotonic deadline before `TaskExecutor` dispatches them either to the asyncio router or a two-process `WorkerPool`. The worker pool independently bounds submitted CPU work so timed-out requests cannot create an unbounded hidden process queue. Retry and circuit breaker remain independent libraries for future remote-peer calls.

**Tech Stack:** Python 3.12, asyncio, `concurrent.futures.ProcessPoolExecutor`, Protobuf, pytest/pytest-asyncio, Ruff, Black, mypy.

**Spec:** `docs/superpowers/specs/2026-09-12-phase2-compute-resilience-design.md`

## Global Constraints

- Python 3.12 compatible.
- One node for Phase 2 development.
- Default CPU workers: 2.
- Default bounded admission/pending capacity: 200.
- Default request timeout: 5 seconds.
- Retry/circuit breaker must not wrap local CPU execution.
- Existing Phase-1 protocol and echo behavior must remain green.

---

### Task 1: Classified compute workloads

**Files:**
- Create: `src/distsys/compute/errors.py`
- Create: `src/distsys/compute/classification.py`
- Modify: `src/distsys/compute/tasks.py`
- Test: `tests/unit/test_classification.py`
- Test: `tests/unit/test_compute_tasks.py`

**Interfaces:**
- Produces: `ExecutionClass.ASYNC`, `ExecutionClass.CPU`.
- Produces: `TaskClassifier.default()`, `register(task_name, execution_class)`, `classify(task_name)`.
- Produces: `TaskValidationError`.
- Produces: `hash_task(payload)`, `sort_task(payload)`, `aggregate_task(payload)`.

- [ ] **Step 1: Write failing classification tests**

```python
classifier = TaskClassifier.default()
assert classifier.classify("echo") is ExecutionClass.ASYNC
assert classifier.classify("hash") is ExecutionClass.CPU
assert classifier.classify("sort") is ExecutionClass.CPU
assert classifier.classify("aggregate") is ExecutionClass.CPU
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src pytest tests/unit/test_classification.py -q`
Expected: import failure because `classification.py` does not exist.

- [ ] **Step 3: Implement classification and CPU tasks**

Use explicit classification, not payload heuristics. Validate hash rounds in `1..1_000_000`; validate sort/aggregate values are JSON numeric arrays; aggregate requires non-empty input.

- [ ] **Step 4: Verify GREEN**

Run: `PYTHONPATH=src pytest tests/unit/test_classification.py tests/unit/test_compute_tasks.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/distsys/compute tests/unit/test_classification.py tests/unit/test_compute_tasks.py
git commit -m "feat: add classified compute workloads"
```

### Task 2: Deadline, backpressure, and token bucket

**Files:**
- Create: `src/distsys/resilience/__init__.py`
- Create: `src/distsys/resilience/deadline.py`
- Create: `src/distsys/resilience/backpressure.py`
- Create: `src/distsys/resilience/rate_limiter.py`
- Test: `tests/unit/test_deadline.py`
- Test: `tests/unit/test_backpressure.py`
- Test: `tests/unit/test_rate_limiter.py`

**Interfaces:**
- `Deadline.after(seconds) -> Deadline`
- `Deadline.remaining() -> float`
- `Deadline.expired() -> bool`
- `Deadline.run(awaitable) -> T`
- `BackpressureController.try_acquire() -> bool`
- `BackpressureController.release() -> None`
- `TokenBucketRateLimiter.allow(cost=1.0) -> bool`

- [ ] **Step 1: Write failing resilience tests**

```python
controller = BackpressureController(capacity=1)
assert await controller.try_acquire()
assert not await controller.try_acquire()
```

```python
limiter = TokenBucketRateLimiter(rate_per_second=10.0, burst=2, clock=fake_clock)
assert limiter.allow()
assert limiter.allow()
assert not limiter.allow()
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src pytest tests/unit/test_deadline.py tests/unit/test_backpressure.py tests/unit/test_rate_limiter.py -q`
Expected: import failures for missing resilience modules.

- [ ] **Step 3: Implement monotonic bounded primitives**

Use `time.monotonic()` for deadlines and refills. Backpressure is deterministic and non-waiting.

- [ ] **Step 4: Verify GREEN**

Run the same focused test command and require all tests to pass.

- [ ] **Step 5: Commit**

```bash
git add src/distsys/resilience tests/unit/test_deadline.py tests/unit/test_backpressure.py tests/unit/test_rate_limiter.py
git commit -m "feat: add bounded admission and deadlines"
```

### Task 3: Bounded process worker pool and execution facade

**Files:**
- Create: `src/distsys/compute/worker_pool.py`
- Create: `src/distsys/compute/executor.py`
- Test: `tests/unit/test_worker_pool.py`
- Test: `tests/unit/test_executor.py`

**Interfaces:**
- `WorkerPool(max_workers=2, max_pending=200)`.
- `WorkerPool.start()`, `execute(fn, *args)`, `close()`.
- `TaskExecutor(router, classifier, worker_pool)`.
- `TaskExecutor.start()`, `execute(task_name, payload, deadline=...)`, `close()`.

- [ ] **Step 1: Write failing worker tests**

```python
pool = WorkerPool(max_workers=1, max_pending=1)
await pool.start()
assert await pool.execute(pow, 2, 10) == 1024
```

Add a cancellation test proving a process slot remains occupied until the underlying process future completes.

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src pytest tests/unit/test_worker_pool.py tests/unit/test_executor.py -q`
Expected: import failures for missing worker/executor modules.

- [ ] **Step 3: Implement process isolation**

Use `multiprocessing.get_context("spawn")`. Submit work directly through `ProcessPoolExecutor.submit`, attach a completion callback to the underlying concurrent future, and release the bounded pending slot only when real process work completes.

- [ ] **Step 4: Verify GREEN**

Run the same focused command and require all tests to pass.

- [ ] **Step 5: Commit**

```bash
git add src/distsys/compute tests/unit/test_worker_pool.py tests/unit/test_executor.py
git commit -m "feat: isolate cpu execution in bounded worker pool"
```

### Task 4: Retry and circuit breaker libraries

**Files:**
- Create: `src/distsys/resilience/retry.py`
- Create: `src/distsys/resilience/circuit_breaker.py`
- Test: `tests/unit/test_retry.py`
- Test: `tests/unit/test_circuit_breaker.py`

**Interfaces:**
- `RetryPolicy(max_attempts=3, base_delay_seconds=0.05, max_delay_seconds=1.0)`.
- `retry_async(operation, policy=..., should_retry=..., deadline=...)`.
- `CircuitBreaker.call(operation)`.
- States: `CLOSED`, `OPEN`, `HALF_OPEN`.

- [ ] **Step 1: Write failing retry/breaker tests**

```python
result = await retry_async(
    operation,
    policy=RetryPolicy(max_attempts=3),
    should_retry=lambda exc: isinstance(exc, ConnectionError),
)
```

Test CLOSED -> OPEN, OPEN rejection, OPEN -> HALF_OPEN after the recovery timeout, successful probe -> CLOSED, and failed probe -> OPEN.

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src pytest tests/unit/test_retry.py tests/unit/test_circuit_breaker.py -q`
Expected: import failures for missing modules.

- [ ] **Step 3: Implement full jitter and breaker state machine**

Full jitter delay is sampled from `[0, min(max_delay, base_delay * 2**retry_index)]`. Do not wire either primitive around local CPU tasks.

- [ ] **Step 4: Verify GREEN**

Run the focused tests and require all to pass.

- [ ] **Step 5: Commit**

```bash
git add src/distsys/resilience tests/unit/test_retry.py tests/unit/test_circuit_breaker.py
git commit -m "feat: add retry and circuit breaker primitives"
```

### Task 5: Protocol and configuration extension

**Files:**
- Modify: `proto/messages.proto`
- Modify/regenerate: `src/distsys/proto/messages_pb2.py`
- Create/regenerate: `src/distsys/proto/messages_pb2.pyi`
- Modify: `src/distsys/protocol/codec.py`
- Modify: `src/distsys/utils/config.py`
- Modify: `.env.example`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Adds `OVERLOADED = 5`.
- Adds `RATE_LIMITED = 6`.
- Adds Phase-2 settings for CPU workers/capacity, rate limiting, retry, and circuit breaker defaults.

- [ ] **Step 1: Write failing enum/config tests**

```python
assert messages_pb2.OVERLOADED == 5
assert messages_pb2.RATE_LIMITED == 6
assert Settings().cpu_workers == 2
assert Settings().cpu_queue_capacity == 200
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=src pytest tests/unit/test_config.py -q`
Expected: missing enum/settings assertions fail.

- [ ] **Step 3: Update schema/config and regenerate**

Run `make proto` on the development machine so both `.py` and `.pyi` are generated from the schema.

- [ ] **Step 4: Verify GREEN**

Run: `PYTHONPATH=src pytest tests/unit/test_config.py tests/unit/test_codec.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add proto src/distsys/proto src/distsys/protocol/codec.py src/distsys/utils/config.py .env.example tests/unit/test_config.py
git commit -m "feat: extend phase two protocol configuration"
```

### Task 6: Node pipeline integration

**Files:**
- Modify: `src/distsys/node.py`
- Test: `tests/integration/test_compute_pipeline.py`
- Test: `tests/integration/test_overload_control.py`
- Test: `tests/integration/test_deadline_behavior.py`
- Test: `tests/integration/test_event_loop_responsiveness.py`
- Keep: `tests/integration/test_single_node.py`

**Interfaces:**
- Node starts/stops the executor.
- Request flow: decode -> rate limit -> admission -> deadline -> executor -> response.
- Maps `WorkerPoolSaturatedError` and admission rejection to `OVERLOADED`.

- [ ] **Step 1: Write failing integration tests**

```python
hashed = await client.request("hash", {"data": "hello", "rounds": 1})
assert hashed["algorithm"] == "sha256"
```

Add tests for structured overload, structured rate limiting, structured timeout, and echo responsiveness while a long CPU hash task runs.

- [ ] **Step 2: Verify RED**

Run the four new integration files. Expected: unknown CPU tasks and missing resilience behavior cause failures.

- [ ] **Step 3: Integrate executor/resilience lifecycle into node**

Register built-in tasks, instantiate a two-worker bounded pool, apply rate limiting and admission before execution, and release request admission in `finally`.

- [ ] **Step 4: Verify GREEN**

Run: `PYTHONPATH=src pytest -q`
Expected: the full suite passes, including all Phase-1 tests.

- [ ] **Step 5: Commit**

```bash
git add src/distsys/node.py tests/integration
git commit -m "feat: integrate compute resilience request pipeline"
```

### Task 7: Tooling, docs, and release verification

**Files:**
- Modify: `Makefile`
- Modify: `pyproject.toml`
- Modify: `requirements-dev.txt`
- Modify: `README.md`
- Modify: `docs/PHASES.md`
- Create: `scripts/phase2_smoke.py`

**Interfaces:**
- `make proto` generates `.py` and `.pyi`.
- `make quality` runs pytest, Ruff, Black, and mypy.
- `phase2_smoke.py` validates echo/hash/sort/aggregate against a running node.

- [ ] **Step 1: Update tooling and documentation**

Pin `grpcio-tools==1.81.1` and `types-protobuf==7.35.1.20260906`; exclude generated Protobuf files from Ruff/Black; document the CPU-timeout non-preemption limitation.

- [ ] **Step 2: Run quality gate**

Run: `make proto && make quality`
Expected: all tests pass, Ruff clean, Black unchanged, mypy clean.

- [ ] **Step 3: Run live smoke**

Start one node with `CPU_WORKERS=2`, run `scripts/phase2_smoke.py`, then run the existing persistent echo smoke with a temporary high benchmark rate limit so the limiter does not intentionally reject the correctness workload.

- [ ] **Step 4: Commit**

```bash
git add Makefile pyproject.toml requirements-dev.txt README.md docs scripts
git commit -m "docs: complete phase two compute resilience"
```

- [ ] **Step 5: Tag after merge/release**

```bash
git tag -a v0.2.0 -m "Phase 2: compute and resilience"
```
