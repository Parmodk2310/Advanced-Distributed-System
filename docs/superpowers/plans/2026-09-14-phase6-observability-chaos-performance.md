# Phase 6 Observability, Chaos, and Performance — TDD Implementation Plan

**Base:** verified Phase 5 commit `3fb542e6804ac0e2cb75b46dbe2d05508ae8dff3`
**Branch:** `phase/6-observability-chaos`
**Rule:** preserve Phase 1–5 correctness/runtime semantics; telemetry failures never fail the data plane.

## Task 1 — Configuration and dependencies
1. Add failing tests for defaults, validation, and env parsing.
2. Add Prometheus/OpenTelemetry runtime dependencies and PyYAML test dependency.
3. Add Phase 6 settings from the approved specification.
4. Verify unit tests, Ruff, Black, mypy.

## Task 2 — Metrics foundation
1. Test dedicated registry isolation, label normalization, histograms, disabled no-op mode.
2. Implement `distsys.observability.metrics.Metrics` with explicit buckets and fixed vocabularies.
3. Explicitly register process/platform/GC collectors on the private registry.
4. Verify no keys, causal tokens, correlation IDs, arbitrary exception text, or CRDT values can become metric labels.

## Task 3 — Health listener and node lifecycle
1. Test `/metrics`, `/health/live`, `/health/ready`, 404/405 behavior, and stable JSON fields.
2. Implement small asyncio-only HTTP server.
3. Start it from `DistributedNode` after app listener binding; stop it idempotently on errors and normal shutdown.
4. Keep observability on a separate port.

## Task 4 — OpenTelemetry and protocol propagation
1. Test tracing-off no-op behavior and W3C inject/extract.
2. Add optional protobuf `traceparent = 6` and `tracestate = 7`; test Phase 5 envelopes still decode.
3. Regenerate protobuf with `make proto` (generated `.py/.pyi` are not hand-edited).
4. Propagate context on peer/CRDT peer calls and extract at inbound node boundary.
5. Bound exporter flush/timeout and drop telemetry failures.

## Task 5 — Core instrumentation
1. Instrument requests, inflight, rate limiting, overload, membership, peer RPCs, replication queue, causal/anti-entropy repair, persistence, coordination, and recovery.
2. Keep label vocabularies bounded; unknown values normalize to `other`.
3. Add spans for request, peer RPC, CRDT, replication, persistence, recovery, and coordination boundaries.
4. Keep correlation IDs in traces/logs only.

## Task 6 — Monitoring topology and dashboard
1. Static-test all YAML/JSON first.
2. Provision pinned Prometheus, Grafana, Tempo, OTel Collector, Toxiproxy, and the dedicated Phase 6 etcd service.
3. Use 2-hour local retention, bounded container log rotation, and no Loki.
4. Provision Prometheus/Tempo data sources and committed `Distributed System — Phase 6` dashboard.
5. Smoke-test 3/3 Prometheus targets, Grafana provisioning, and a trace retrievable from Tempo.

## Task 7 — Reproducible benchmarks
1. Test nearest-rank p50/p95/p99, serialization, validity/correctness rules, and bounded concurrency.
2. Implement immutable benchmark models and runner using monotonic high-resolution timing.
3. Record git/dirty state, UTC, Python/OS/kernel/CPU/memory/WSL/container metadata.
4. Write atomic JSON to ignored `benchmark-results/`.
5. Quick guard: success ratio >= 0.99, p95 < 0.500 s, zero correctness failures.
6. Laptop default: one worker/node, concurrency 16, 10 s warm-up, 30 s measured window.

## Task 8 — Safe chaos controller
1. Test explicit opt-in, manifest targets, duration bounds, PID identity, LIFO/idempotent cleanup, Toxiproxy rollback.
2. Implement only `node-kill`, `network-delay`, `partition`, `etcd-outage`.
3. Every mutation registers cleanup before application.
4. Docker commands always use project `distsys-phase6` and the exact Phase 6 compose file.
5. Node kill validates `/proc/<pid>` start token and command identity; restart uses only the target-specific managed launcher.
6. Peer endpoint rewriting is active only when `RUN_CHAOS_TESTS=1`; normal Phase 1–5 routing is unchanged.

## Task 9 — Release gate and evidence
1. Add Phase 6 Make targets.
2. Run `make quality` without Docker.
3. Start dedicated stack/cluster, run observability + monitoring smoke, all four chaos scenarios, task+CRDT quick benchmarks.
4. Verify cleanup: no toxics, no managed PIDs, Phase 6 ports free, no generated DB/cert/result tracked.
5. Re-run Phase 5 secure smoke and full regression in the real checkout.
6. Record fresh output in `docs/PHASE6_VERIFICATION.md` before marking Phase 6 complete.

## Acceptance
The acceptance checklist is the ten criteria from the approved design specification. No throughput number is a hardware-independent promise; correctness and evidence outrank headline performance.
