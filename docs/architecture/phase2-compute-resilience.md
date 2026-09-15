# Phase 2 — Compute and Resilience

**Status: IMPLEMENTED AND VERIFIED**

Phase 2 protects the event loop and bounds overload before dispatching I/O or CPU-heavy work.

![Phase 2 architecture](assets/phase2-architecture.svg)

## GitHub-native diagram

```mermaid
flowchart LR
  Q["Request"] --> D["Monotonic deadline"] --> L["Rate limiter"] --> B["Bounded admission"]
  B --> C["Workload classifier"]
  C --> I["Async I/O router"] --> O["Response / structured error"]
  C --> P["Bounded process pool"] --> O
```

## Source mapping

- `src/distsys/compute/`: classification, task execution and bounded process workers.
- `src/distsys/resilience/`: backpressure, rate limiting, deadlines, retry and circuit breaking.
- `src/distsys/node.py`: ordered request-pipeline integration.

One monotonic deadline is preserved through admission and execution. Retry and circuit breaking remain scoped primitives. Phase 2 is still a single-node runtime.
