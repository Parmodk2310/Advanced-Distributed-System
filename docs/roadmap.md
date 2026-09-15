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

## Phase 5 — Secure Persistence & Recovery

Implemented/owned:

- `src/distsys/persistence/{models,codec,repository,executor,migrations,sqlite_repository,durable_store,backup}.py`
- `src/distsys/coordination/{models,client,etcd_client,lease,discovery,service}.py`
- `src/distsys/security/{tls_context,certificate,identity}.py`
- `src/distsys/recovery/{restore,reconciliation,coordinator}.py`
- `src/distsys/health/state.py`
- durable SQLite/WAL repository with schema v1 and migrations
- stable node installation UUID and durable causal actor/counter/frontier
- staged causal allocation and atomic CRDT+causal persistence
- persist-before-memory remote replication/repair merges
- bounded persistence admission/backpressure
- safe SQLite online backup
- etcd-backed member discovery and lease coordination
- post-start etcd degradation/recovery without replacing SWIM
- TLS 1.3 secure listener/client contexts
- mutual TLS authentication and logical node SAN verification
- recovery readiness gating and stale-replica reconciliation
- `scripts/generate_dev_certs.sh`
- `scripts/run_phase5_cluster.sh`
- `scripts/phase5_smoke.py`
- `scripts/phase5_restart_smoke.py`
- `scripts/phase5_etcd_smoke.py`
- `scripts/phase5_verify.sh`
- local etcd Docker Compose topology and live-etcd integration gate

Exit: acknowledged CRDT mutations are locally durable before ACK; the same durable node resumes its causal actor/counter after restart while SWIM uses a fresh process incarnation; stale durable replicas reconcile rather than overwrite newer state; peers use TLS 1.3/mTLS with node identity verification; and a temporary post-ready etcd outage degrades coordination without unnecessarily stopping the existing SWIM/CRDT data plane. Phase 5 still does not claim quorum durability, consensus, linearizability, exactly-once execution, or distributed transactions.

## Phase 6 — Observability, Chaos & Performance

Status: **COMPLETE**

Verified implementation checkpoint:

```text
296fdd8
```

Implemented/owned:

- `src/distsys/observability/*`
- `src/distsys/benchmarking/*`
- `src/distsys/chaos/*`
- independent `/metrics`, `/health/live`, and `/health/ready`
- bounded-cardinality Prometheus instrumentation
- OpenTelemetry/W3C trace propagation
- OTLP Collector → Tempo trace path
- provisioned Prometheus/Grafana monitoring
- Dockerized three-node Phase 6 runtime
- direct healthy-baseline peer routing
- opt-in Toxiproxy peer/etcd routing for chaos
- staged infrastructure/proxy/node/monitoring startup
- managed chaos manifest and safety policy
- network-delay scenario
- peer-partition scenario
- etcd-outage scenario
- Docker container node-kill/recovery scenario
- task and CRDT benchmark workloads
- reproducible JSON benchmark artifacts with environment metadata
- direct/proxy release-gate lifecycle
- `deploy/monitoring/Dockerfile.node`
- `deploy/monitoring/docker-compose.yml`
- `deploy/monitoring/prometheus/*`
- `deploy/monitoring/grafana/*`
- `deploy/monitoring/tempo/*`
- `deploy/monitoring/otel-collector/*`
- `scripts/benchmark.py`
- `scripts/chaos.py`
- `scripts/phase6_observability_smoke.py`
- `scripts/phase6_monitoring_smoke.py`
- `scripts/phase6_proxy_bootstrap.py`
- `scripts/run_phase6_cluster.sh`
- `scripts/phase6_release_gate.sh`
- Phase 6 unit/integration/contract coverage
- `docs/architecture/phase6-observability-chaos-performance.md`
- `docs/verification/phase6.md`

Final verification:

```text
373 passed, 8 skipped
Ruff          PASS
Black         PASS
mypy          PASS
compileall    PASS

Prometheus    3/3 targets healthy
Grafana       provisioned
Tempo         trace round-trip PASS

task quick    valid=true, success_ratio=1.0
CRDT quick    valid=true, success_ratio=1.0

network-delay PASS, cleanup_ok=true
partition     PASS, cleanup_ok=true
etcd-outage   PASS, cleanup_ok=true
node-kill     PASS, cleanup_ok=true

Phase 6 release gate passed
```

Exit: the secure/durable Phase 5 cluster is now observable, benchmarkable, and fault-tested through a reproducible release gate. Healthy benchmark traffic bypasses chaos proxies; chaos traffic explicitly opts into managed Toxiproxy paths. Monitoring and tracing stay outside the correctness-critical data path. All tested faults recover and clean up successfully.

Phase 6 does not claim consensus, linearizability, quorum durability, exactly-once execution, distributed transactions, arbitrary fault tolerance, or production Kubernetes readiness.

---

## Phase 7 — Production Delivery & Portfolio

Status: **LOCAL KUBERNETES IMPLEMENTED; AWS DEMONSTRATION PENDING SEPARATE APPROVAL**

Implemented/owned:

- `Dockerfile`
- `deploy/helm/distributed-system/*`
- `deploy/kind/*` and optional `deploy/k3d/*`
- `scripts/phase7/*`
- `.github/workflows/phase7-*`
- `deploy/terraform/aws/*` with `enable_eks=false` by default
- `docs/runbooks/phase7-*`
- `docs/verification/phase7.md`

Local exit: repeatable non-root image delivery, three-node StatefulSet, ephemeral mTLS, persistent restart, rollback, CI gates, and cleanup. Cloud exit remains pending an approved exact plan, temporary EKS verification, same-day destroy, and zero-resource evidence.
