# Phase 5 WSL Network Hotfix

This hotfix changes only integration-test networking. It does not modify production networking code.

## Root cause

WSL's localhost forwarding/interception can make dynamically assigned `127.0.0.1` ports unreliable for in-WSL integration tests. Standalone tests now use the Linux guest's routed IPv4 address when WSL is detected and continue using `127.0.0.1` on ordinary Linux/CI.

## Apply

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate
git switch phase/5-secure-persistence

rm -rf /tmp/phase5-wsl-network-hotfix
mkdir -p /tmp/phase5-wsl-network-hotfix

unzip -q \
  "/mnt/c/Users/HP/Downloads/phase5-wsl-network-hotfix.zip" \
  -d /tmp/phase5-wsl-network-hotfix

rsync -av \
  /tmp/phase5-wsl-network-hotfix/phase5-wsl-network-hotfix/ \
  ./
```

## Format and lint

```bash
python -m black \
  tests/integration/network_hosts.py \
  tests/integration/test_network_hosts.py \
  tests/integration/test_single_node.py

python -m ruff check --fix \
  tests/integration/network_hosts.py \
  tests/integration/test_network_hosts.py \
  tests/integration/test_single_node.py

python -m black \
  tests/integration/network_hosts.py \
  tests/integration/test_network_hosts.py \
  tests/integration/test_single_node.py
```

## Focused verification

```bash
python -m pytest -q \
  tests/integration/test_network_hosts.py \
  tests/integration/test_single_node.py \
  tests/integration/test_cross_key_causal_session.py \
  tests/unit/test_replication_outbox.py \
  tests/integration/test_network_helpers.py \
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
