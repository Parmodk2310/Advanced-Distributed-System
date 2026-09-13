# Phase 5 WSL Test Stability Hotfix

Apply this hotfix on top of the existing Phase-5 + `phase5-wsl-hotfix.zip` working tree.

It changes only test infrastructure:

- standalone node integration tests bind with `port=0` and use `node.bound_port`, removing the free-port time-of-check/time-of-use race seen under WSL;
- cluster integration timings use realistic local scheduling budgets (`ping=0.25s`, `indirect=0.25s`, `suspicion=0.75s`) instead of a 30 ms direct-ping timeout that intermittently marked healthy peers unavailable on WSL.

Apply:

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate

rm -rf /tmp/phase5-wsl-stability-hotfix
mkdir -p /tmp/phase5-wsl-stability-hotfix
unzip -q "/mnt/c/Users/HP/Downloads/phase5-wsl-stability-hotfix.zip" -d /tmp/phase5-wsl-stability-hotfix
rsync -av /tmp/phase5-wsl-stability-hotfix/phase5-wsl-stability-hotfix/ ./

python -m black tests/integration/cluster_helpers.py tests/integration/test_single_node.py
python -m ruff check --fix tests/integration/cluster_helpers.py tests/integration/test_single_node.py
python -m black tests/integration/cluster_helpers.py tests/integration/test_single_node.py
```

Focused verification:

```bash
python -m pytest -q \
  tests/integration/test_single_node.py \
  tests/integration/test_anti_entropy_convergence.py::test_digest_anti_entropy_repairs_state_missed_by_fast_replication \
  tests/integration/test_crdt_async_replication.py::test_gcounter_state_replicates_to_three_node_replica_set \
  tests/integration/test_mvregister_concurrent_partition.py::test_concurrent_register_values_survive_then_causal_resolution_wins \
  tests/integration/test_crdt_node_rejoin.py::test_rejoined_node_gets_new_actor_and_reconstructs_empty_store
```

Expected: `12 passed`.

Then run:

```bash
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
```
