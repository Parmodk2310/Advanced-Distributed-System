# Apply Phase 4 — Causal Consistency & CRDT Replication

This overlay is intended for the verified `v0.3.0` codebase on branch
`phase/4-causal-crdt`.

## 1. Confirm branch and baseline

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate

git branch --show-current
git status
git merge-base --is-ancestor v0.3.0 HEAD \
  && echo "v0.3.0 baseline OK"
```

Use a clean `phase/4-causal-crdt` branch before applying the overlay.

## 2. Extract and apply the overlay

```bash
rm -rf /tmp/phase4-overlay
mkdir -p /tmp/phase4-overlay

unzip \
  "/mnt/c/Users/HP/Downloads/distributed-system-phase4-overlay.zip" \
  -d /tmp/phase4-overlay

rsync -av \
  /tmp/phase4-overlay/distributed-system-phase4-overlay/ \
  ~/projects/distributed-system-phase1/
```

## 3. Regenerate Protobuf in WSL

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate
make proto
```

The sandbox artifact contains a runtime-compatible checked-in Protobuf module,
but `make proto` is the authoritative developer generation step using the pinned
`grpcio-tools==1.81.1` available in your WSL environment.

## 4. Format and verify

```bash
python -m black src tests scripts
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
```

The sandbox implementation suite contains 222 tests. Your WSL run is the
authoritative gate for pytest + Ruff + Black + mypy after Protobuf regeneration.

## 5. Run the normal three-node Phase-4 smoke

Terminal 1:

```bash
make phase4-cluster
```

Terminal 2:

```bash
make phase4-smoke
```

Expected final markers include:

```text
phase3_membership_converged=PASS
gcounter_remote_causal_read=PASS
causal_read_repair_performed=<true|false>
orset_operations=PASS
mvregister_operation=PASS
phase4_smoke=PASS
```

`causal_read_repair_performed` may be `false` in the normal smoke when fast
asynchronous replication reaches the reader before the read. The managed smoke
below creates a deterministic stale-rejoin case and requires targeted causal repair.

Stop Terminal 1 with `Ctrl+C`, then verify ports are free:

```bash
for port in 18000 18001 18002; do
  ss -ltnp | grep ":$port" || echo "Port $port is free"
done
```

## 6. Run managed failure/rejoin verification

```bash
python scripts/phase4_smoke.py \
  --host 127.0.0.1 \
  --ports 18000 18001 18002 \
  --managed-command 'bash scripts/run_phase4_cluster.sh'
```

Expected markers:

```text
phase4_managed_failure_detection=PASS
phase4_reduced_rf_write=PASS
phase4_rejoin_new_causal_epoch=PASS
phase4_rejoin_targeted_causal_repair=PASS
phase4_rejoin_recovery=PASS
```

## 7. Release rule

Do not create `v0.4.0` until the feature branch is reviewed/merged and the full
quality gate plus Phase-4 normal and managed smoke are rerun on merged `main`.
