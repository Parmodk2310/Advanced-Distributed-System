# Phase 6 Implementation Notes

## Design review decision

The approved specification is suitable for implementation. It correctly prioritizes reproducible evidence and correctness over headline throughput, keeps observability off the data-plane correctness path, bounds metric cardinality, limits chaos to a dedicated local project, and uses laptop-safe defaults.

## One implementation clarification

A membership-based distributed system normally reconnects to the host/port advertised by the peer. If Toxiproxy is placed only on bootstrap addresses, steady-state peer RPCs can bypass it after membership exchange. Phase 6 therefore adds `distsys.chaos.routing.resolve_peer_endpoint()` as an **opt-in chaos-profile rewrite**:

- ignored unless `RUN_CHAOS_TESTS=1`;
- only rewrites explicitly named node IDs in `PHASE6_PEER_PROXY_MAP`;
- defaults to the original host/port for every other case;
- carries no effect in normal Phase 1–5 operation.

This keeps network-delay/partition experiments real without changing advertised membership or production routing semantics.

## Correctness boundary

`DistributedNode` remains the Phase 5 implementation. `ObservedDistributedNode` calls the existing methods and wraps boundaries for telemetry. It does not introduce an alternate task, CRDT, persistence, recovery, or coordination path.

## Cardinality policy

Prometheus label vocabularies are enumerated. Unknown values become `other`. Keys, CRDT values, causal tokens, correlation IDs, exception messages, paths, certificates and secrets never become metric labels. Correlation IDs may appear on spans and existing JSON logs.

## Performance interpretation

The quick local `>=99% success`, `<500 ms p95`, and zero-correctness-failure checks are regression guards for the local profile. They are not portable throughput or latency promises across hardware.
