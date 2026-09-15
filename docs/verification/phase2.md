# Phase 2 Verification Record

Verification performed in the artifact build environment on 2026-09-12.

## Functional suite

Command:

```bash
PYTHONPATH=src python -m pytest -q
```

Result:

```text
54 passed in 3.74s
```

## Syntax compilation

Command:

```bash
python -m compileall -q src scripts tests
```

Result: success.

## Live built-in task smoke

A real node was started on localhost with `CPU_WORKERS=2` and a temporary high benchmark rate limit. The following live tasks returned valid responses:

- `echo`
- `hash`
- `sort`
- `aggregate`

## 10K persistent protocol correctness run

The rate limiter was temporarily raised so the test measured protocol correctness instead of intentional admission rejection.

Result:

```text
requests=10000
success=10000
failures=0
mismatches=0
elapsed_seconds=0.973
requests_per_second=10282.30
p50_ms=0.083
p95_ms=0.155
p99_ms=0.260
```

These numbers are environment-specific validation measurements, not project performance claims.

## Static quality tools

Ruff, Black, and mypy are part of the project `make quality` gate. They were not available in the artifact build container and the container has no package-index network access, so those three tools must be rerun in the user's existing WSL virtual environment after `make proto`. The user's Phase-1 environment already has these tools installed.
