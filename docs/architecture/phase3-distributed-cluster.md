# Phase 3 — Distributed Cluster

**Status: IMPLEMENTED AND VERIFIED**

Phase 3 evolves the runtime into a decentralized three-node cluster with deterministic ownership and failure-aware routing.

![Phase 3 architecture](assets/phase3-architecture.svg)

## GitHub-native diagram

```mermaid
flowchart TB
  C["Client + routing key"] --> H["SHA-256 consistent-hash ring"]
  H --> N0["node-0"] & N1["node-1"] & N2["node-2"]
  N0 <--> |"gossip + one-hop tasks"| N1
  N1 <--> |"gossip + one-hop tasks"| N2
  N2 <--> |"gossip + one-hop tasks"| N0
  F["SWIM-lite probes + incarnation state"] -.-> N0 & N1 & N2
```

## Source mapping

- `src/distsys/cluster/`: membership, gossip, failure detection, peer transport, consistent hashing and routing.
- `src/distsys/node.py`: cluster lifecycle and routed request integration.

Static seeds bootstrap membership; gossip decentralizes it. Direct and indirect probes drive `ALIVE → SUSPECT → DEAD`, while incarnations support safe rejoin. Routing is best-effort/idempotent, not exactly once.
