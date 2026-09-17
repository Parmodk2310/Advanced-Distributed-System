# Phase 1–7 Architecture Package Design

## Status

Implemented architecture package, updated after the verified Phase 7 delivery lifecycle.

Phases 1–7 describe implemented and verified behavior. Phase 7 must be labeled **VERIFIED TEMPORARY LIFECYCLE** and must not imply permanent hosting or multi-AZ availability.

## Purpose

Create one coherent architecture package that lets:

- a recruiter understand the project’s progression and differentiation quickly;
- a senior engineer trace each claim to real components, runtime boundaries, verification evidence, and explicit limitations;
- a future contributor understand what each phase adds without overstating the bounded Phase 7 cloud evidence.

## Deliverables

Create eight architecture subjects:

1. Phase 1 — Foundation and Single Node
2. Phase 2 — Compute and Resilience
3. Phase 3 — Distributed Cluster
4. Phase 4 — Causal Consistency and CRDT Replication
5. Phase 5 — Secure Persistence and Recovery
6. Phase 6 — Observability, Chaos and Performance
7. Phase 7 — Production Delivery and Cloud Deployment
8. Phase 1–7 — Cumulative Evolution Overview

Each subject has:

- one explanatory Markdown page;
- Mermaid source for GitHub-native rendering;
- Graphviz DOT source for deterministic external rendering;
- one rendered SVG for immediate visual inspection.

## Repository Layout

```text
docs/architecture/
├── README.md
├── phase1-foundation.md
├── phase2-compute-resilience.md
├── phase3-distributed-cluster.md
├── phase4-causal-crdt.md
├── phase5-secure-persistence.md
├── phase6-observability-chaos-performance.md
├── phase7-production-delivery.md
├── phase1-7-evolution.md
└── assets/
    ├── phase1-architecture.{mmd,dot,svg}
    ├── phase2-architecture.{mmd,dot,svg}
    ├── phase3-architecture.{mmd,dot,svg}
    ├── phase4-architecture.{mmd,dot,svg}
    ├── phase5-architecture.{mmd,dot,svg}
    ├── phase6-architecture.{mmd,dot,svg}
    ├── phase7-architecture.{mmd,dot,svg}
    └── phase1-7-evolution.{mmd,dot,svg}
```

The existing Phase 6 page and assets are retained and normalized in place rather than duplicated.

## Shared Visual Contract

All diagrams use the same visual vocabulary:

- blue: client, API, protocol and ingress;
- green: implemented compute or data-plane components;
- amber: resilience, coordination and recovery;
- purple: persistence, replication and state;
- teal: observability and operational tooling;
- gray dashed boundary: external infrastructure;
- red dashed path: controlled fault or failure path;
- pale gray: external or separately managed infrastructure boundaries.

Every Phase 1–7 diagram displays implemented status. Phase 7 representations additionally state that the verified AWS lifecycle was temporary.

Diagrams use a top-down or left-to-right flow with no more than five nodes on one horizontal rank. Labels use domain language first and source identifiers only where they improve traceability.

## Phase Architecture Content

### Phase 1 — Foundation and Single Node

Show the client, length-prefixed TCP framing, Protobuf envelope, asynchronous node, task router, I/O tasks, bounded message validation and response path.

Primary source mappings include:

- `src/distsys/client.py`
- `src/distsys/node.py`
- `src/distsys/protocol/`
- `src/distsys/compute/router.py`
- `src/distsys/compute/tasks.py`

The diagram must not imply distributed behavior.

### Phase 2 — Compute and Resilience

Show one monotonic deadline flowing through rate limiting, bounded admission, workload classification, async I/O execution and the bounded process worker pool. Include retry and circuit-breaker primitives as reusable boundaries, not as global retry wrappers.

Primary source mappings include:

- `src/distsys/compute/`
- `src/distsys/resilience/`
- the Phase 2 request pipeline in `src/distsys/node.py`

The diagram must make event-loop isolation and overload behavior visible.

### Phase 3 — Distributed Cluster

Show three nodes, static seed bootstrap, decentralized membership, SWIM-lite direct/indirect probing, gossip, incarnation-aware state, consistent-hash ownership, one-hop forwarding and deterministic failover.

Primary source mappings include:

- `src/distsys/cluster/`
- peer transport and routing integration in `src/distsys/node.py`

The diagram must state that routing is best-effort/idempotent and does not provide exactly-once execution.

### Phase 4 — Causal Consistency and CRDT Replication

Show client causal tokens, dotted mutation identity, local-first CRDT operations, RF=3 replica selection, asynchronous state replication, targeted causal repair and digest-based anti-entropy.

Primary source mappings include:

- `src/distsys/causal/`
- `src/distsys/crdt/`
- `src/distsys/storage/`
- `src/distsys/replication/`
- `src/distsys/crdt_service.py`
- `src/distsys/crdt_client.py`

Show GCounter, PNCounter, ORSet and MVRegister without implying consensus, quorum durability or linearizability.

### Phase 5 — Secure Persistence and Recovery

Show persist-before-memory mutation flow, SQLite/WAL, stable installation identity, schema migration, online backup, restart restoration, stale-replica reconciliation, readiness gating, etcd discovery/leases and TLS 1.3 mutual authentication.

Primary source mappings include:

- `src/distsys/persistence/`
- `src/distsys/recovery/`
- `src/distsys/coordination/`
- `src/distsys/security/`
- `src/distsys/health/`

The diagram must distinguish local durability from quorum durability and coordination state from replicated application state.

### Phase 6 — Observability, Chaos and Performance

Preserve the implemented direct-versus-proxy profile distinction. Show three nodes, etcd, Prometheus, Grafana, OpenTelemetry Collector, Tempo, Toxiproxy, benchmark drivers, chaos controller and recovery verification.

Primary mappings include:

- `src/distsys/observability/`
- `src/distsys/benchmarking/`
- `src/distsys/chaos/`
- `deploy/monitoring/`
- Phase 6 scripts and release gate

Telemetry remains outside the correctness-critical path. Healthy benchmark traffic bypasses Toxiproxy; chaos traffic explicitly opts into proxy routing.

### Phase 7 — Production Delivery and Cloud Deployment

Label the diagram **VERIFIED TEMPORARY LIFECYCLE**.

Show the approved promotion path:

```text
one immutable container image
        ↓
local kind/k3d validation
        ↓
Helm release contract
        ↓
Terraform-provisioned AWS EKS
```

Include container registry, Kubernetes workloads/services/configuration, Helm, Terraform, AWS EKS, load balancing, managed state boundaries, secrets integration, CI quality/security/release gates and rollback. The same release artifact must be promoted from local validation to AWS rather than rebuilt per environment.

Phase 7 must preserve every Phase 1–6 correctness and release-gate boundary.

### Phase 1–7 Evolution Overview

Present a recruiter-first progression:

```text
Protocol
→ Bounded execution
→ Multi-node routing
→ Causal replicated state
→ Durable secure recovery
→ Observable fault-tested runtime
→ Verified production delivery lifecycle
```

The overview communicates capability accumulation: later phases extend earlier guarantees rather than replacing them.

## Markdown Page Contract

Each phase page contains:

1. status;
2. one-sentence phase objective;
3. rendered SVG;
4. GitHub-native Mermaid;
5. component-to-source mapping;
6. request, state or control flow explanation;
7. guarantees added in that phase;
8. explicit non-guarantees;
9. links to the design specification, verification evidence and roadmap where available.

The architecture index summarizes all eight diagrams in a compact table and identifies Phase 7 as verified with a temporary AWS lifecycle.

## README Integration

Add a concise Architecture section linking to:

- the cumulative overview;
- the architecture index;
- the current Phase 6 architecture;
- the verified Phase 7 delivery lifecycle.

Do not duplicate deep technical detail in the README.

## Accuracy and Safety Rules

- Do not change runtime code, tests, dependencies, deployment configuration or release scripts.
- Do not modify or move `v0.6.0`.
- Do not claim permanent Phase 7 hosting, multi-AZ availability or unrestricted production readiness.
- Do not claim consensus, linearizability, quorum durability, exactly-once execution, distributed transactions or arbitrary fault tolerance.
- Every implemented component label must map to an existing path or documented behavior.
- Dates may appear inside historical evidence but not in active architecture filenames.
- Do not reintroduce `docs/superpowers/` or root-level delivery artifacts.

## Verification

Before completion:

1. verify all eight Mermaid sources are syntactically parseable;
2. verify all eight DOT sources with Graphviz;
3. render all eight SVG files from their DOT sources;
4. confirm each SVG is non-empty and contains its phase status;
5. validate all relative Markdown links;
6. validate every Phase 1–6 source mapping against the repository tree;
7. scan Phase 7 files for the verified temporary-lifecycle label and honest limitations;
8. compare the final diff and confirm no runtime or configuration file changed;
9. run the existing Quality workflow on the final commit.

The full Docker chaos/performance release gate is unnecessary because this package changes documentation and diagram assets only.

## Completion Criteria

The package is complete when all eight subjects exist in Markdown, Mermaid, DOT and SVG; all links and source mappings validate; Phase 7 is documented as a verified temporary lifecycle without implying permanent or multi-AZ hosting; the README exposes the architecture set; the repository Quality workflow passes; and `v0.6.0` remains unchanged.
