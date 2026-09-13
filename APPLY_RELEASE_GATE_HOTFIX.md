# Phase 5 Release-Gate Hotfix

Apply this after the earlier Phase-5 WSL/outbox hotfixes.

It fixes the last two release-gate failures:

1. Cross-key causal session writes: a new CRDT key may proceed when this node's already-observed global causal frontier dominates the client's session token. This prevents an unrelated same-key repair from failing a valid new-key write such as the secure-smoke MVRegister write.
2. WSL standalone-node test ports: single-node integration tests now use `port=0` so Linux atomically selects a free loopback port. Shutdown is still verified by rebinding the actual bound port after `stop()`.

Apply:

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate
git switch phase/5-secure-persistence

rm -rf /tmp/phase5-release-gate-hotfix
mkdir -p /tmp/phase5-release-gate-hotfix
unzip -q "/mnt/c/Users/HP/Downloads/phase5-release-gate-hotfix.zip" -d /tmp/phase5-release-gate-hotfix
rsync -av /tmp/phase5-release-gate-hotfix/phase5-release-gate-hotfix/ ./
```

Format/lint:

```bash
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
  tests/unit/test_replication_outbox.py \
  tests/integration/test_network_helpers.py \
  tests/integration/test_anti_entropy_convergence.py::test_digest_anti_entropy_repairs_state_missed_by_fast_replication \
  tests/integration/test_crdt_async_replication.py::test_gcounter_state_replicates_to_three_node_replica_set \
  tests/integration/test_mvregister_concurrent_partition.py::test_concurrent_register_values_survive_then_causal_resolution_wins \
  tests/integration/test_crdt_node_rejoin.py::test_rejoined_node_gets_new_actor_and_reconstructs_empty_store
```

Then run the release gates:

```bash
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
make phase5-etcd-integration
make phase5-secure-smoke
```
