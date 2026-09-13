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

## Phase 3 — Distributed Cluster

Implemented/owned:

- `src/distsys/cluster/member.py`
- `src/distsys/cluster/membership.py`
- `src/distsys/cluster/codec.py`
- `src/distsys/cluster/consistent_hash.py`
- `src/distsys/cluster/peer_client.py`
- `src/distsys/cluster/failure_detector.py`
- `src/distsys/cluster/gossip.py`
- `src/distsys/cluster/cluster_router.py`
- `src/distsys/cluster/service.py`
- protocol additions for join, probes, gossip, routed and forwarded requests
- optional `routing_key` client API
- `cluster.whoami` diagnostic routing task
- static-seed bootstrap + decentralized gossip membership
- SWIM-lite direct/indirect failure detection
- incarnation-aware `ALIVE -> SUSPECT -> DEAD` state
- SHA-256 consistent hashing with 64 virtual nodes by default
- single-hop task forwarding with shared deadlines
- Phase-2 retry/circuit-breaker integration for peer task transport
- deterministic candidate failover
- `scripts/run_phase3_cluster.sh`
- `scripts/phase3_smoke.py`
- Phase-3 unit/integration coverage

Exit: three nodes bootstrap and converge, detect failure, remove unhealthy members from ownership, route keyed work to deterministic owners, fail over idempotent work, and admit restarted nodes with newer incarnations. Delivery remains best-effort/idempotent rather than exactly once.

## Phase 4 — Causal Consistency & CRDT Replication

Implemented/owned:

- `src/distsys/causal/{actor,dot,version_vector,token,clock}.py`
- `src/distsys/crdt/{base,types,gcounter,pncounter,orset,mvregister}.py`
- `src/distsys/storage/{models,crdt_store}.py`
- `src/distsys/replication/{codec,replica_selector,outbox,replicator,causal_repair,digest,anti_entropy,peer_client,service}.py`
- `src/distsys/crdt_service.py`
- `src/distsys/crdt_client.py`
- typed Protobuf causal/CRDT messages and error codes
- incarnation-scoped causal actors and dotted mutation identities
- session-wide VersionVector/CausalToken semantics
- GCounter, PNCounter, observed-remove ORSet, and MVRegister
- Phase-3 consistent-hash replica placement with RF=3 by default
- primary-less local-first writes
- bounded generation-safe coalescing replication outbox
- asynchronous state-based fan-out with bounded retry
- targeted causal read/write repair
- digest-driven replica-aware anti-entropy
- empty-store restart/rejoin reconstruction
- topology-transparent `CrdtClient` and single-hop any-node ingress
- `scripts/run_phase4_cluster.sh` and `scripts/phase4_smoke.py`

Exit: client sessions preserve read-your-writes, monotonic reads, monotonic writes, and writes-follow-reads; concurrent ORSet/MVRegister updates converge without clock-based conflict loss; missed replication is repaired by causal fetch or anti-entropy; and restarted replicas rejoin with a new causal actor epoch and reconstruct assigned in-memory state. Phase 4 intentionally does not claim durable acknowledgements, quorum durability, exactly-once execution, transactions, or disk persistence.

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
