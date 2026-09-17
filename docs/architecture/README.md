# Architecture Guide

This guide covers the verified seven-phase architecture. Phase 7 includes local Kubernetes delivery and a controlled, temporary AWS EKS demonstration that used one worker and was destroyed after evidence capture; it does not establish permanent hosting or multi-AZ readiness.

| Phase | Architecture focus | Status | Diagram |
| --- | --- | --- | --- |
| 1 | Framed protocol and asynchronous single node | Implemented and verified | [View](phase1-foundation.md) |
| 2 | Bounded compute and resilience controls | Implemented and verified | [View](phase2-compute-resilience.md) |
| 3 | Membership, routing and failure detection | Implemented and verified | [View](phase3-distributed-cluster.md) |
| 4 | Causal metadata and CRDT convergence | Implemented and verified | [View](phase4-causal-crdt.md) |
| 5 | Persistence, recovery, coordination and mTLS | Implemented and verified | [View](phase5-secure-persistence.md) |
| 6 | Observability, chaos and performance | Implemented and verified | [View](phase6-observability-chaos-performance.md) |
| 7 | Kubernetes and temporary AWS EKS lifecycle | **Verified; one-worker demo, destroyed** | [View](phase7-production-delivery.md) |
| 1–7 | Cumulative capability evolution | **Complete** | [View](phase1-7-evolution.md) |

## Visual language

- Blue: client, protocol and ingress.
- Green: implemented compute or data-plane behavior.
- Amber: resilience, coordination and recovery.
- Purple: persistence, replication and state.
- Gray dashed: planned or external infrastructure.
- Red dashed: controlled fault paths where applicable.

The durable design contract is [Phase 1–7 Architecture Package Design](../design/phase1-7-architecture-package.md). The full progression is summarized in [Phase 1–7 Evolution](phase1-7-evolution.md).
