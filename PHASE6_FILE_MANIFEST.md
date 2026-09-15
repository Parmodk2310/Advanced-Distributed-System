# Phase 6 File Manifest

## New runtime source

- `src/distsys/observed_node.py`
- `src/distsys/observability/__init__.py`
- `src/distsys/observability/metrics.py`
- `src/distsys/observability/health.py`
- `src/distsys/observability/tracing.py`
- `src/distsys/benchmarking/__init__.py`
- `src/distsys/benchmarking/model.py`
- `src/distsys/benchmarking/aggregate.py`
- `src/distsys/benchmarking/stats.py`
- `src/distsys/benchmarking/runner.py`
- `src/distsys/chaos/__init__.py`
- `src/distsys/chaos/model.py`
- `src/distsys/chaos/safety.py`
- `src/distsys/chaos/toxiproxy.py`
- `src/distsys/chaos/routing.py`

## New operational files

- `deploy/monitoring/docker-compose.yml`
- `deploy/monitoring/prometheus/prometheus.yml`
- `deploy/monitoring/otel-collector/config.yml`
- `deploy/monitoring/tempo/tempo.yml`
- Grafana datasource/dashboard provisioning and `phase6-overview.json`
- `scripts/phase6_proxy_bootstrap.py`
- `scripts/phase6_start_node.sh`
- `scripts/run_phase6_cluster.sh`
- `scripts/phase6_observability_smoke.py`
- `scripts/phase6_monitoring_smoke.py`
- `scripts/benchmark.py`
- `scripts/chaos.py`
- `scripts/phase6_release_gate.sh`
- `scripts/phase6_verify.sh`

## New tests

- observability metrics/health/tracing tests;
- benchmark model/statistics/formal-aggregation tests;
- chaos safety/cleanup/routing tests;
- config and trace-envelope compatibility tests;
- monitoring provisioning and real-node endpoint integration tests;
- opt-in chaos and performance environment tests.

## Existing files changed by `patches/apply_existing_file_changes.py`

- `pyproject.toml`
- `requirements.txt`
- `requirements-dev.txt`
- `.env.example`
- `.gitignore`
- `src/distsys/utils/config.py`
- `proto/messages.proto`
- `src/distsys/protocol/message.py`
- `src/distsys/protocol/codec.py`
- `src/distsys/cluster/peer_client.py`
- `src/distsys/replication/peer_client.py`
- `src/distsys/node.py` (small wiring only; core logic is not replaced)
- `src/distsys/replication/service.py`
- `src/distsys/persistence/durable_store.py`
- `src/distsys/main.py`
- `Makefile`

## Generated, not hand-edited

- `src/distsys/proto/messages_pb2.py`
- `src/distsys/proto/messages_pb2.pyi`

Generate them with `make proto` after applying the source `.proto` change.

## v5 recovery note

No Phase 6 directory was moved or renamed. v5 changes existing Phase 6 files in place and adds no Phase 7 source. It retains repeated-partial-patch recovery, makes observability listener startup deterministic on WSL/Python 3.12, and adjusts only the two scheduler-sensitive Phase 1–5 DEAD-state integration waits from 2.0s to 3.0s without changing runtime failure-detector behavior.

Additional regression coverage: `tests/unit/patches/test_phase6_patcher_recovery.py`.
