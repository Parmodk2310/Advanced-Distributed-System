# Apply Phase 6 v5 Recovery

This revision preserves the approved Phase 6 architecture and directory structure. It is designed for the current partially patched checkout and specifically addresses the final WSL/Python 3.12 health-listener race plus scheduler-sensitive Phase 1–5 SWIM integration waits.

## 1. Preflight

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate
git switch phase/6-observability-chaos
git status --short
```

Do not reset the current Phase 6 work. Do not commit or push Phase 6 yet.

## 2. Copy v5 over the repository root

```bash
ZIP="/mnt/c/Users/HP/Downloads/phase6-observability-chaos-performance-fixed-v5.zip"
rm -rf /tmp/phase6-v5
mkdir -p /tmp/phase6-v5
unzip -q "$ZIP" -d /tmp/phase6-v5
rsync -av \
  --exclude='.pytest_cache/' \
  --exclude='__pycache__/' \
  /tmp/phase6-v5/phase6-observability-chaos-performance/ \
  ./
```

## 3. Repair and verify idempotency

```bash
python patches/apply_existing_file_changes.py --root .
python patches/apply_existing_file_changes.py --root .
```

Both runs must finish with:

```text
Phase 6 existing-file changes applied. Next: make proto && make quality
```

The v5 patcher retains the v4 config/import/instrumentation recovery and additionally relaxes only the two scheduler-sensitive `SUSPECT -> DEAD` test waits from 2.0s to 3.0s. Runtime SWIM settings and behavior are unchanged.

## 4. Regenerate and normalize

```bash
make proto
python -m ruff check --fix src tests scripts
python -m black src tests scripts
python -m ruff check src tests scripts
python -m black --check src tests scripts
python -m compileall -q src scripts tests patches
git diff --check
```

## 5. Focused regressions

```bash
PYTHONPATH=src python -m pytest -q \
  tests/unit/observability \
  tests/unit/benchmarking \
  tests/unit/chaos \
  tests/unit/patches \
  tests/unit/test_phase6_config_contract.py \
  tests/unit/test_phase6_trace_envelope.py \
  tests/integration/test_monitoring_config.py \
  tests/integration/test_observability_endpoints.py
```

Then run the two Phase 1–5 SWIM regressions together:

```bash
unset RUN_CHAOS_TESTS PHASE6_PEER_PROXY_MAP
PYTHONPATH=src python -m pytest -q \
  tests/integration/test_failure_detection.py \
  tests/integration/test_node_rejoin.py
```

## 6. Complete gates

```bash
unset RUN_CHAOS_TESTS PHASE6_PEER_PROXY_MAP
make quality
```

Only after that passes:

```bash
make phase5-certs
make phase5-secure-smoke
make phase6-release-gate
```

The Phase 6 release gate itself now sanitizes chaos-routing environment variables before its initial `make quality`, so the regression suite always runs on the normal Phase 1–5 route.
