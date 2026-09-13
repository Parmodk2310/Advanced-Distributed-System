# Phase 5 WSL Loopback Port Hotfix

This hotfix changes integration-test infrastructure only. It does not alter production networking behavior.

It replaces hard-coded standalone-node ports with a helper that:

1. rejects ports already accepting connections,
2. verifies the node can bind the port,
3. verifies the started listener is reachable before yielding the node,
4. waits for the port to become unreachable after shutdown.

Apply from the repository root:

```bash
rsync -av /path/to/phase5-port-hotfix/ ./
```

Then run:

```bash
python -m black tests/integration/cluster_helpers.py tests/integration/test_single_node.py tests/integration/test_network_helpers.py
python -m ruff check --fix tests/integration/cluster_helpers.py tests/integration/test_single_node.py tests/integration/test_network_helpers.py
python -m black tests/integration/cluster_helpers.py tests/integration/test_single_node.py tests/integration/test_network_helpers.py

python -m pytest -q \
  tests/integration/test_network_helpers.py \
  tests/integration/test_single_node.py \
  tests/integration/test_cross_key_causal_session.py \
  tests/integration/test_anti_entropy_convergence.py::test_digest_anti_entropy_repairs_state_missed_by_fast_replication \
  tests/integration/test_crdt_async_replication.py::test_gcounter_state_replicates_to_three_node_replica_set \
  tests/integration/test_mvregister_concurrent_partition.py::test_concurrent_register_values_survive_then_causal_resolution_wins \
  tests/integration/test_crdt_node_rejoin.py::test_rejoined_node_gets_new_actor_and_reconstructs_empty_store
```
