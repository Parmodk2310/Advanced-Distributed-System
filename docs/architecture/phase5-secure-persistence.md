# Phase 5 — Secure Persistence and Recovery

**Status: IMPLEMENTED AND VERIFIED**

Phase 5 makes local acknowledgements durable, restores node state after restart and secures peer identity.

![Phase 5 architecture](assets/phase5-architecture.svg)

## GitHub-native diagram

```mermaid
flowchart TB
  M["Validated mutation"] --> A["Persistence admission"] --> C["Staged causal + CRDT state"]
  C --> DB["SQLite WAL transaction"] --> MEM["Install in memory"] --> R["Async replication"] --> ACK["ACK · local durability"]
  DB --> REST["Restart restore"] --> REC["Replica reconciliation"] --> READY["READY"]
  ETCD["etcd discovery + TTL leases"] -.-> REC
  TLS["TLS 1.3 + mTLS identity"] -.-> R
```

## Source mapping

- `src/distsys/persistence/`: SQLite/WAL repository, migrations, durable adapter and backup.
- `src/distsys/recovery/`: restore and reconciliation orchestration.
- `src/distsys/coordination/`: etcd registration, leases and discovery.
- `src/distsys/security/`: TLS contexts, certificate identity and trust checks.
- `src/distsys/health/`: readiness state.

An ACK means the local SQLite transaction committed before memory installation. This is local durability—not quorum durability. etcd holds coordination state, not authoritative CRDT application state.
