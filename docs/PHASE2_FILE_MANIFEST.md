# Phase 2 File Manifest

## New production files

- `src/distsys/compute/classification.py`
- `src/distsys/compute/errors.py`
- `src/distsys/compute/executor.py`
- `src/distsys/compute/worker_pool.py`
- `src/distsys/resilience/__init__.py`
- `src/distsys/resilience/backpressure.py`
- `src/distsys/resilience/circuit_breaker.py`
- `src/distsys/resilience/deadline.py`
- `src/distsys/resilience/rate_limiter.py`
- `src/distsys/resilience/retry.py`

## Modified production/protocol/config files

- `.env.example`
- `proto/messages.proto`
- `src/distsys/__init__.py`
- `src/distsys/client.py`
- `src/distsys/compute/tasks.py`
- `src/distsys/node.py`
- `src/distsys/proto/messages_pb2.py`
- `src/distsys/proto/messages_pb2.pyi`
- `src/distsys/protocol/codec.py`
- `src/distsys/protocol/message.py`
- `src/distsys/utils/config.py`

`src/distsys/main.py` and `src/distsys/compute/router.py` remain compatible and require no behavioral change.

## New unit tests

- `tests/unit/test_backpressure.py`
- `tests/unit/test_circuit_breaker.py`
- `tests/unit/test_classification.py`
- `tests/unit/test_compute_tasks.py`
- `tests/unit/test_config.py`
- `tests/unit/test_deadline.py`
- `tests/unit/test_executor.py`
- `tests/unit/test_rate_limiter.py`
- `tests/unit/test_retry.py`
- `tests/unit/test_worker_pool.py`

## Modified/retained unit tests

- `tests/unit/test_codec.py`
- `tests/unit/test_framing.py`
- `tests/unit/test_message.py`
- `tests/unit/test_router.py`

## New integration tests

- `tests/integration/test_compute_pipeline.py`
- `tests/integration/test_deadline_behavior.py`
- `tests/integration/test_event_loop_responsiveness.py`
- `tests/integration/test_overload_control.py`

## Existing integration regression coverage

- `tests/integration/test_single_node.py`

## Tooling/scripts/docs

- `Makefile`
- `pyproject.toml`
- `requirements-dev.txt`
- `README.md`
- `docs/PHASES.md`
- `docs/PHASE2_FILE_MANIFEST.md`
- `docs/superpowers/specs/2026-09-12-phase2-compute-resilience-design.md`
- `docs/superpowers/plans/2026-09-12-phase2-compute-resilience.md`
- `scripts/phase2_smoke.py`
- `scripts/smoke_test.py`

## Required regeneration step on the development machine

The package includes a checked-in compatible `messages_pb2.py`/`.pyi`, but the project standard is to regenerate them with the pinned local toolchain after applying Phase 2:

```bash
make proto
```

That uses `grpcio-tools==1.81.1` and generates both runtime Python and typing stubs from `proto/messages.proto`.

## Recommended Phase-2 validation

```bash
make proto
make quality
```

Then run one live node and:

```bash
python scripts/phase2_smoke.py --host 127.0.0.1 --port 18000
```

For the 10K protocol correctness run, temporarily raise the server's rate-limit settings as documented in `README.md`; otherwise the default rate limiter is expected to reject a very fast local benchmark client.
