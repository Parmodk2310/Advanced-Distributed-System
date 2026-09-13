# Phase 5 Final WSL Hotfix

This hotfix is applied on top of the current `phase/5-secure-persistence` tree after the earlier Phase-5 overlay/hotfixes.

It fixes two root causes:

1. **Replication outbox reservation race**: a completed in-flight generation could remove a peer/key entry after a follow-up write had reserved it but before that follow-up published. The pending entry now tracks outstanding reservations and remains pinned until publish/cancel.
2. **WSL loopback test instability**: integration tests no longer infer Linux listener shutdown from Windows/WSL localhost-forwarding behavior. Single-node tests use known stable ports and verify clean shutdown by rebinding the Linux port.

Apply:

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate
git switch phase/5-secure-persistence

rm -rf /tmp/phase5-final-wsl-hotfix
mkdir -p /tmp/phase5-final-wsl-hotfix

unzip -q \
  "/mnt/c/Users/HP/Downloads/phase5-final-wsl-hotfix.zip" \
  -d /tmp/phase5-final-wsl-hotfix

rsync -av \
  /tmp/phase5-final-wsl-hotfix/phase5-final-wsl-hotfix/ \
  ./
```

Format/lint:

```bash
python -m black \
  src/distsys/replication/outbox.py \
  tests/unit/test_replication_outbox.py \
  tests/integration/cluster_helpers.py \
  tests/integration/test_single_node.py \
  tests/integration/test_network_helpers.py

python -m ruff check --fix \
  src/distsys/replication/outbox.py \
  tests/unit/test_replication_outbox.py \
  tests/integration/cluster_helpers.py \
  tests/integration/test_single_node.py \
  tests/integration/test_network_helpers.py

python -m black \
  src/distsys/replication/outbox.py \
  tests/unit/test_replication_outbox.py \
  tests/integration/cluster_helpers.py \
  tests/integration/test_single_node.py \
  tests/integration/test_network_helpers.py
```

Focused verification:

```bash
python -m pytest -q \
  tests/unit/test_replication_outbox.py \
  tests/integration/test_network_helpers.py \
  tests/integration/test_single_node.py \
  tests/integration/test_cross_key_causal_session.py \
  tests/integration/test_anti_entropy_convergence.py::test_digest_anti_entropy_repairs_state_missed_by_fast_replication \
  tests/integration/test_crdt_async_replication.py::test_gcounter_state_replicates_to_three_node_replica_set \
  tests/integration/test_mvregister_concurrent_partition.py::test_concurrent_register_values_survive_then_causal_resolution_wins \
  tests/integration/test_crdt_node_rejoin.py::test_rejoined_node_gets_new_actor_and_reconstructs_empty_store
```

Then:

```bash
make quality
PYTHONPATH=src python -m compileall -q src scripts tests
make phase5-etcd-integration
make phase5-secure-smoke
```
