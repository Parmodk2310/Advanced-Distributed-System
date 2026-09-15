# Phase 4 — Causal Consistency and CRDT Replication

**Status: IMPLEMENTED AND VERIFIED**

Phase 4 adds primary-less replicated state with client-session causal guarantees and deterministic convergence.

![Phase 4 architecture](assets/phase4-architecture.svg)

## GitHub-native diagram

```mermaid
flowchart LR
  T["Client causal token"] --> V["Causal validation"] --> D["Dotted mutation"]
  D --> C["Local CRDT merge"] --> R["RF=3 replica selection"] --> A["Async state replication"] --> X["Converged replicas"]
  P["Targeted causal repair"] --> X
  E["Digest anti-entropy"] --> X
```

## Source mapping

- `src/distsys/causal/`: actors, dots, version vectors, tokens and clocks.
- `src/distsys/crdt/`: GCounter, PNCounter, ORSet and MVRegister.
- `src/distsys/storage/`: in-memory CRDT state.
- `src/distsys/replication/`: placement, outbox, replication, repair and anti-entropy.
- `src/distsys/crdt_service.py` and `src/distsys/crdt_client.py`: service and client boundaries.

The system provides read-your-writes, monotonic reads/writes and writes-follow-reads for supported sessions. It does not claim consensus, linearizability, quorum durability or distributed transactions.
