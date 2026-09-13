# Phase 5 Final WSL/Causal Hotfix

This hotfix is applied **after** `phase5-wsl-hotfix.zip` and `phase5-wsl-stability-hotfix.zip`.

It contains two fixes:

1. `tests/integration/test_single_node.py` uses explicit fixed loopback ports (`21001..21008`) instead of WSL2 ephemeral ports. This avoids current WSL loopback port-tracking failures affecting `port=0` and rapidly churned ephemeral test ports.
2. `src/distsys/crdt_service.py` allows creation of a new CRDT key when the node's local causal frontier already dominates the session token. It no longer requires unrelated same-key peer repair for a cross-key dependency that is already locally observed.

It also adds a regression test in `test_cross_key_causal_session.py` that disables replication before writing the second key, proving the local causal frontier is sufficient.

Apply:

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate
git switch phase/5-secure-persistence

rm -rf /tmp/phase5-final-hotfix
mkdir -p /tmp/phase5-final-hotfix
unzip -q "/mnt/c/Users/HP/Downloads/phase5-final-hotfix.zip" -d /tmp/phase5-final-hotfix
rsync -av /tmp/phase5-final-hotfix/phase5-final-hotfix/ ./

python -m black \
  src/distsys/crdt_service.py \
  tests/integration/test_cross_key_causal_session.py \
  tests/integration/test_single_node.py

python -m ruff check --fix \
  src/distsys/crdt_service.py \
  tests/integration/test_cross_key_causal_session.py \
  tests/integration/test_single_node.py

python -m black \
  src/distsys/crdt_service.py \
  tests/integration/test_cross_key_causal_session.py \
  tests/integration/test_single_node.py
```

Focused verification:

```bash
python -m pytest -q \
  tests/integration/test_single_node.py \
  tests/integration/test_cross_key_causal_session.py \
  tests/integration/test_anti_entropy_convergence.py::test_digest_anti_entropy_repairs_state_missed_by_fast_replication \
  tests/integration/test_crdt_async_replication.py::test_gcounter_state_replicates_to_three_node_replica_set \
  tests/integration/test_mvregister_concurrent_partition.py::test_concurrent_register_values_survive_then_causal_resolution_wins \
  tests/integration/test_crdt_node_rejoin.py::test_rejoined_node_gets_new_actor_and_reconstructs_empty_store
```

Then run:

```bash
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
make phase5-etcd-integration
make phase5-secure-smoke
```
