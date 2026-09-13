# Apply Phase 5 to the v0.4.0 Repository

This overlay is intended for the Phase-5 feature branch based on the verified `v0.4.0` release.

## 1. Verify the branch and baseline

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate

git switch phase/5-secure-persistence
git merge-base --is-ancestor v0.4.0 HEAD && echo "v0.4.0 baseline OK"
git status --short
```

Keep your already committed Phase-5 design specification in place.

## 2. Apply the overlay

```bash
rm -rf /tmp/phase5-overlay
mkdir -p /tmp/phase5-overlay

unzip \
  "/mnt/c/Users/HP/Downloads/phase5-overlay.zip" \
  -d /tmp/phase5-overlay

rsync -av \
  /tmp/phase5-overlay/phase5-overlay/ \
  ~/projects/distributed-system-phase1/
```

## 3. Install/update dependencies

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Phase 5 adds `etcd3gw>=2.7,<3`; development tooling retains the existing pytest/Ruff/Black/mypy/`grpcio-tools` requirements.

## 4. Regenerate Protobuf and run the local quality gate

```bash
make proto
python -m black src tests scripts
python -m ruff check --fix src tests scripts
python -m black src tests scripts
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
```

All commands must exit zero before committing implementation code.

## 5. Run real etcd integration

Docker must be available from WSL (Docker Desktop WSL integration is sufficient).

```bash
make phase5-etcd-integration
```

This forces the three normally gated live-etcd tests to run instead of skip.

## 6. Run the complete secure smoke

```bash
make phase5-secure-smoke
```

Required final marker:

```text
PHASE5_SMOKE=PASS
```

The smoke also verifies mTLS, durable CRDTs, restart recovery, causal-actor continuity, etcd degradation/recovery, and negative TLS paths.

## 7. Check repository hygiene

```bash
git status --short
git diff --check

if git ls-files | grep -E '(\.key$|certs/generated|\.db$|\.db-wal$|\.db-shm$)'; then
  echo "Sensitive/runtime artifact is tracked"
  exit 1
fi
```

Do not create or push the `v0.5.0` tag until these WSL gates pass and the feature branch is reviewed and merged into `main`.
