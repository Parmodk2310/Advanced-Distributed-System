# Phase 6 Implementation Bundle — v5 Repair

Base: `3fb542e6804ac0e2cb75b46dbe2d05508ae8dff3`

This bundle keeps the approved **Observability, Chaos, and Performance** architecture and existing Phase 6 directory structure. v5 keeps the v4 recovery work and targets the final WSL/Python 3.12 health-listener race plus scheduler-sensitive SWIM integration waits.

## v5 fixes

- replication patch anchor now matches the unique constructor pair instead of the repeated `_anti_entropy_started = False` line;
- patcher can upgrade already-applied v2 cluster/CRDT peer wrappers in place and can be rerun idempotently;
- normal Phase 1–5 peer traffic fast-paths directly to the original transport when metrics, tracing, and chaos interception are inactive;
- observability startup now binds and listens on the socket explicitly before asyncio takes ownership, eliminating the immediate-connect race seen on Python 3.12/WSL;
- remaining benchmark `TRY004` findings now raise `TypeError` for invalid CRDT value types;
- chaos controller keeps its intentional scenario-wide exception boundary with a stable short `noqa` comment;
- chaos routing now exposes an explicit activation predicate used by the normal-path fast path;
- the two Phase 1–5 SWIM integration tests keep the same SUSPECT/DEAD assertions but use a 3.0s DEAD wait budget instead of 2.0s to avoid scheduler flakes under the full suite;
- the release gate sanitizes chaos-routing environment variables before `make quality`;
- benchmark aggregation and the earlier mTLS identity fixes remain included.

## Architecture remains unchanged

Phase 6 still consists of the additive observed node, Prometheus metrics, OpenTelemetry/Tempo tracing, Grafana dashboards, Toxiproxy-based guarded chaos, deterministic benchmark tooling, and release-gate scripts. No Phase 7 code is included.

Use `APPLY_PHASE6.md` for the exact recovery commands for the current partially applied checkout.


## v5 recovery

The patcher can normalize repeated partial-application state, including duplicate Phase 6 config kwargs, missing chaos-routing imports, and already-instrumented replication/persistence methods.
