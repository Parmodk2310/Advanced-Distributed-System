# Apply Phase 3 to the Existing Repository

Use the overlay only when the checkout is already at the merged Phase-2 (`v0.2.0`) baseline and the current branch is `phase/3-distributed-cluster`.

## 1. Confirm branch and clean working tree

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate

git branch --show-current
git status --short
```

Expected branch:

```text
phase/3-distributed-cluster
```

The working tree should be clean before applying the overlay.

## 2. Extract and copy the overlay

Example when the ZIP is in the Windows Downloads folder:

```bash
rm -rf /tmp/phase3-overlay
mkdir -p /tmp/phase3-overlay

unzip "/mnt/c/Users/HP/Downloads/distributed-system-phase3-overlay.zip" \
  -d /tmp/phase3-overlay

rsync -av \
  /tmp/phase3-overlay/distributed-system-phase3-overlay/ \
  ./
```

## 3. Regenerate Protobuf and run the authoritative quality gate

```bash
make proto
make quality
```

Do not commit or tag Phase 3 if pytest, Ruff, Black, or mypy fails.

## 4. Run the three-node inspection smoke

Terminal 1:

```bash
make phase3-cluster
```

Terminal 2:

```bash
make phase3-smoke
```

Stop the runner in Terminal 1 with `Ctrl+C` after the inspection smoke.

## 5. Run the managed failure/failover/rejoin smoke

Make sure ports 18000, 18001, and 18002 are free first. Then run:

```bash
PYTHONPATH=src python scripts/phase3_smoke.py \
  --host 127.0.0.1 \
  --ports 18000 18001 18002 \
  --managed-command "bash scripts/run_phase3_cluster.sh"
```

Expected managed assertions:

```text
managed_failure_detection=PASS
managed_failover=PASS
managed_rejoin=PASS
```

## 6. Release rule

Do not create `v0.3.0` until the feature branch is reviewed/merged into `main` and `make quality` passes again on the merged `main` branch.
