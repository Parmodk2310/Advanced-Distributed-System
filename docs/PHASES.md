# Seven-Phase Implementation Map

## Phase 1 — Foundation & Single Node

Files introduced/owned:

- `pyproject.toml`
- `requirements.txt`
- `requirements-dev.txt`
- `proto/messages.proto`
- `src/distsys/main.py`
- `src/distsys/node.py`
- `src/distsys/client.py`
- `src/distsys/proto/messages_pb2.py`
- `src/distsys/protocol/{message,framing,codec,errors}.py`
- `src/distsys/compute/{router,tasks}.py`
- `src/distsys/utils/{config,logging}.py`
- `tests/unit/*`
- `tests/integration/test_single_node.py`
- `scripts/smoke_test.py`

Exit: clean install, protocol tests green, single-node echo, 10K sequential smoke test.

## Phase 2 — Compute & Resilience

Add/modify:

- `src/distsys/compute/classification.py`
- `src/distsys/compute/errors.py`
- `src/distsys/compute/worker_pool.py`
- `src/distsys/compute/executor.py`
- `src/distsys/compute/tasks.py`
- `src/distsys/resilience/backpressure.py`
- `src/distsys/resilience/rate_limiter.py`
- `src/distsys/resilience/deadline.py`
- `src/distsys/resilience/retry.py`
- `src/distsys/resilience/circuit_breaker.py`
- `proto/messages.proto` (`OVERLOADED`, `RATE_LIMITED`)
- `src/distsys/node.py` request-pipeline integration
- `tests/unit/test_classification.py`
- `tests/unit/test_compute_tasks.py`
- `tests/unit/test_worker_pool.py`
- `tests/unit/test_executor.py`
- `tests/unit/test_backpressure.py`
- `tests/unit/test_rate_limiter.py`
- `tests/unit/test_deadline.py`
- `tests/unit/test_retry.py`
- `tests/unit/test_circuit_breaker.py`
- `tests/integration/test_compute_pipeline.py`
- `tests/integration/test_overload_control.py`
- `tests/integration/test_deadline_behavior.py`
- `tests/integration/test_event_loop_responsiveness.py`
- `scripts/phase2_smoke.py`

Exit: CPU work is isolated from the event loop, admission is bounded, structured overload/rate-limit/deadline behavior is verified, and retry/circuit-breaker primitives are ready for Phase-3 remote calls.

## Phase 3 — Three-Node Cluster

Add:

- `src/distsys/cluster/member.py`
- `src/distsys/cluster/membership.py`
- `src/distsys/cluster/gossip.py`
- `src/distsys/cluster/failure_detector.py`
- `src/distsys/cluster/consistent_hash.py`
- `src/distsys/cluster/peer_client.py`
- `src/distsys/cluster/router.py`
- `tests/unit/test_membership.py`
- `tests/unit/test_failure_detector.py`
- `tests/unit/test_consistent_hash.py`
- `tests/integration/test_three_node_cluster.py`
- `tests/integration/test_gossip_convergence.py`
- `tests/integration/test_node_failure_reroute.py`
- `scripts/run_cluster.py`

Exit: three nodes converge, detect loss, and remap only affected keys.

## Phase 4 — Causal Consistency & CRDT Replication

Add:

- `src/distsys/consistency/vector_clock.py`
- `src/distsys/consistency/store.py`
- `src/distsys/consistency/replicator.py`
- `src/distsys/consistency/crdt/base.py`
- `src/distsys/consistency/crdt/g_counter.py`
- `src/distsys/consistency/crdt/pn_counter.py`
- `src/distsys/consistency/crdt/lww_register.py`
- `src/distsys/consistency/crdt/or_set.py`
- `tests/unit/test_vector_clock.py`
- `tests/unit/test_g_counter.py`
- `tests/unit/test_pn_counter.py`
- `tests/unit/test_lww_register.py`
- `tests/unit/test_or_set.py`
- `tests/integration/test_crdt_replication.py`
- `tests/integration/test_partition_merge.py`

Extend Protobuf with causal metadata and CRDT messages. Exit: partitioned concurrent updates deterministically converge.

## Phase 5 — Security, Persistence & Recovery

Add:

- `src/distsys/security/tls.py`
- `src/distsys/security/identity.py`
- `src/distsys/storage/repository.py`
- `src/distsys/storage/etcd.py`
- `src/distsys/storage/snapshot.py`
- `certs/generate.sh` (development only; private keys ignored)
- `tests/integration/test_mtls.py`
- `tests/integration/test_etcd_recovery.py`
- `tests/integration/test_restart_restore.py`
- `tests/integration/test_etcd_degraded_mode.py`

Exit: mTLS authenticates peers, state survives restart, and etcd outage does not crash the request data plane.

## Phase 6 — Observability, Chaos & Performance

Add:

- `src/distsys/observability/metrics.py`
- `src/distsys/observability/health.py`
- `src/distsys/observability/tracing.py`
- `deploy/monitoring/prometheus.yml`
- `deploy/monitoring/grafana/provisioning/*`
- `deploy/monitoring/grafana/dashboards/distributed-system.json`
- `scripts/benchmark.py`
- `scripts/chaos.py`
- `tests/chaos/test_node_kill.py`
- `tests/chaos/test_network_delay.py`
- `tests/chaos/test_partition.py`
- `tests/chaos/test_etcd_outage.py`
- `tests/performance/test_latency_budget.py`
- `docs/benchmark-methodology.md`

Exit: dashboards explain normal/overload/failure behavior and benchmark results are reproducible with environment metadata.

## Phase 7 — Production Delivery & Portfolio

Add:

- `Dockerfile`
- `compose.yaml`
- `compose.monitoring.yaml`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `deploy/terraform/aws/*` or `deploy/terraform/gcp/*`
- optional `deploy/kubernetes/base/*`
- optional `deploy/helm/distributed-system/*`
- `docs/architecture.md`
- `docs/protocol.md`
- `docs/consistency.md`
- `docs/failure-model.md`
- `docs/security.md`
- `docs/runbook.md`
- `docs/performance-report.md`
- `docs/recruiter-summary.md`

Exit: repeatable deployment, CI quality gates, reproducible benchmark report, known limitations, and a recruiter/senior-engineer-ready README.
