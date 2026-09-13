# Phase 3 File Manifest

## New production cluster modules

- `src/distsys/cluster/__init__.py`
- `src/distsys/cluster/member.py`
- `src/distsys/cluster/membership.py`
- `src/distsys/cluster/codec.py`
- `src/distsys/cluster/consistent_hash.py`
- `src/distsys/cluster/peer_client.py`
- `src/distsys/cluster/failure_detector.py`
- `src/distsys/cluster/gossip.py`
- `src/distsys/cluster/cluster_router.py`
- `src/distsys/cluster/service.py`

## Modified production files

- `proto/messages.proto`
- `src/distsys/proto/messages_pb2.py` (generated)
- `src/distsys/proto/messages_pb2.pyi` (generated)
- `src/distsys/protocol/message.py`
- `src/distsys/protocol/codec.py`
- `src/distsys/client.py`
- `src/distsys/node.py`
- `src/distsys/compute/tasks.py`
- `src/distsys/compute/classification.py`
- `src/distsys/utils/config.py`
- `src/distsys/__init__.py`
- `.env.example`
- `.gitignore`
- `pyproject.toml`
- `Makefile`

## New Phase-3 unit tests

- `tests/unit/test_member.py`
- `tests/unit/test_membership.py`
- `tests/unit/test_cluster_codec.py`
- `tests/unit/test_consistent_hash.py`
- `tests/unit/test_cluster_config.py`
- `tests/unit/test_peer_client.py`
- `tests/unit/test_cluster_router.py`
- `tests/unit/test_failure_detector.py`
- `tests/unit/test_gossip.py`
- `tests/unit/test_cluster_service.py`
- `tests/unit/test_cluster_logging.py`

## Modified Phase-1/2 unit regression tests

- `tests/unit/test_classification.py`
- `tests/unit/test_codec.py`
- `tests/unit/test_compute_tasks.py`
- `tests/unit/test_message.py`

## New/modified Phase-3 integration tests

- `tests/integration/cluster_helpers.py`
- `tests/integration/test_cluster_join.py`
- `tests/integration/test_gossip_convergence.py`
- `tests/integration/test_failure_detection.py`
- `tests/integration/test_distributed_routing.py`
- `tests/integration/test_routing_failover.py`
- `tests/integration/test_node_rejoin.py`
- `tests/integration/test_cluster_control_under_load.py`
- `tests/integration/test_single_node.py`

All Phase-3 network integration tests allocate explicit free ports through pytest's `unused_tcp_port_factory` rather than relying on direct `port=0` test configuration.

## Scripts

- `scripts/run_phase3_cluster.sh`
- `scripts/phase3_smoke.py`

## Documentation

- `README.md`
- `docs/PHASES.md`
- `docs/PHASE3_FILE_MANIFEST.md`
- `docs/PHASE3_VERIFICATION.md`
- `docs/superpowers/specs/2026-09-13-phase3-distributed-cluster-design.md`
- `docs/superpowers/plans/2026-09-13-phase3-distributed-cluster.md`
- `APPLY_PHASE3.md`
