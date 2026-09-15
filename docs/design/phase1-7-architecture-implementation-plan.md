# Phase 1–7 Architecture Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver seven phase-specific architecture diagrams plus one cumulative evolution diagram in Markdown, Mermaid, DOT and rendered SVG.

**Architecture:** Use one shared visual contract but select the diagram structure that best explains each phase: request flow for Phases 1–2, topology and control flow for Phase 3, state flow for Phases 4–5, operational topology for Phase 6, deployment topology for Phase 7, and capability progression for the cumulative overview. Phases 1–6 describe verified implementation; Phase 7 is visibly planned.

**Tech Stack:** Markdown, Mermaid flowcharts, Graphviz DOT/SVG, GitHub Actions quality verification.

**Spec:** `docs/design/phase1-7-architecture-package.md`

## Global Constraints

- Work directly on `main`; do not create a branch or pull request.
- Do not modify runtime code, tests, dependencies, deployment configuration or release scripts.
- Preserve the `v0.6.0` tag.
- Phase 1–6 diagrams must say `IMPLEMENTED AND VERIFIED`.
- Phase 7 diagrams and pages must say `PLANNED — NOT IMPLEMENTED`.
- Do not claim consensus, linearizability, quorum durability, exactly-once execution, distributed transactions, arbitrary fault tolerance or production readiness.
- Use stable filenames without calendar dates.
- Do not create `docs/superpowers/`, root delivery files or permanent execution scaffolding.
- Delete this implementation-plan file after the completed architecture package has passed verification.

---

## File Map

**Create:**

- `docs/architecture/README.md`
- `docs/architecture/phase1-foundation.md`
- `docs/architecture/phase2-compute-resilience.md`
- `docs/architecture/phase3-distributed-cluster.md`
- `docs/architecture/phase4-causal-crdt.md`
- `docs/architecture/phase5-secure-persistence.md`
- `docs/architecture/phase7-production-delivery.md`
- `docs/architecture/phase1-7-evolution.md`
- `docs/architecture/assets/phase1-architecture.{mmd,dot,svg}`
- `docs/architecture/assets/phase2-architecture.{mmd,dot,svg}`
- `docs/architecture/assets/phase3-architecture.{mmd,dot,svg}`
- `docs/architecture/assets/phase4-architecture.{mmd,dot,svg}`
- `docs/architecture/assets/phase5-architecture.{mmd,dot,svg}`
- `docs/architecture/assets/phase7-architecture.{mmd,dot,svg}`
- `docs/architecture/assets/phase1-7-evolution.{mmd,dot,svg}`

**Modify:**

- `README.md`
- `docs/architecture/phase6-observability-chaos-performance.md`
- `docs/architecture/assets/phase6-architecture.mmd`
- `docs/architecture/assets/phase6-architecture.dot`
- `docs/architecture/assets/phase6-architecture.svg`

**Delete after verification:**

- `docs/design/phase1-7-architecture-implementation-plan.md`

---

### Task 1: Establish the architecture index and visual contract

**Files:**
- Create: `docs/architecture/README.md`
- Reference: `docs/design/phase1-7-architecture-package.md`

**Interfaces:**
- Consumes: status and visual rules from the approved specification.
- Produces: canonical navigation and shared legend used by every phase page.

- [ ] **Step 1: Write the architecture index**

Create a compact table with columns `Phase`, `Architecture focus`, `Status`, and `Diagram`. Link all eight pages. Add the shared color legend and the distinction between implemented Phases 1–6 and planned Phase 7.

- [ ] **Step 2: Validate all intended links are represented**

Run:

```bash
python - <<'PY'
from pathlib import Path
text = Path("docs/architecture/README.md").read_text()
expected = [
    "phase1-foundation.md", "phase2-compute-resilience.md",
    "phase3-distributed-cluster.md", "phase4-causal-crdt.md",
    "phase5-secure-persistence.md",
    "phase6-observability-chaos-performance.md",
    "phase7-production-delivery.md", "phase1-7-evolution.md",
]
missing = [name for name in expected if name not in text]
assert not missing, missing
print("architecture index contract: PASS")
PY
```

Expected: `architecture index contract: PASS`.

- [ ] **Step 3: Commit the index with the first complete diagram task**

Do not create an index-only commit with broken links. Include it with Task 2.

---

### Task 2: Create Phase 1 foundation architecture

**Files:**
- Create: `docs/architecture/phase1-foundation.md`
- Create: `docs/architecture/assets/phase1-architecture.mmd`
- Create: `docs/architecture/assets/phase1-architecture.dot`
- Create: `docs/architecture/assets/phase1-architecture.svg`
- Include: `docs/architecture/README.md`

**Interfaces:**
- Consumes: `TaskClient`, framing, codec, `DistributedNode`, `TaskRouter`, task handlers.
- Produces: canonical Phase 1 request/response flow.

- [ ] **Step 1: Write Mermaid and DOT sources**

Use these exact semantic nodes and edges:

```text
Client
→ length-prefixed TCP framing
→ Protobuf envelope validation
→ asynchronous DistributedNode
→ TaskRouter
→ I/O task handler
→ encoded response
→ Client
```

Add a side boundary for configuration and structured logging. Include `IMPLEMENTED AND VERIFIED`. Do not show peers, replication, persistence or external coordination.

- [ ] **Step 2: Render the SVG**

Run:

```bash
dot -Tsvg docs/architecture/assets/phase1-architecture.dot   -o docs/architecture/assets/phase1-architecture.svg
```

Expected: exit 0 and a non-empty SVG.

- [ ] **Step 3: Write the Markdown page**

Include status, objective, SVG, Mermaid, source mapping, request flow, guarantees and non-guarantees. Map labels to `src/distsys/client.py`, `src/distsys/node.py`, `src/distsys/protocol/`, `src/distsys/compute/router.py` and `src/distsys/compute/tasks.py`.

- [ ] **Step 4: Validate and commit**

Run `dot -Tsvg` again, confirm page links resolve, then commit:

```bash
git add docs/architecture/README.md docs/architecture/phase1-foundation.md   docs/architecture/assets/phase1-architecture.*
git commit -m "docs: add phase 1 foundation architecture"
```

---

### Task 3: Create Phase 2 compute and resilience architecture

**Files:**
- Create: `docs/architecture/phase2-compute-resilience.md`
- Create: `docs/architecture/assets/phase2-architecture.{mmd,dot,svg}`

**Interfaces:**
- Consumes: request pipeline and Phase 2 compute/resilience modules.
- Produces: bounded admission and workload-isolation flow.

- [ ] **Step 1: Model the request path**

Use:

```text
Request
→ one monotonic deadline
→ token-bucket rate limiter
→ bounded backpressure admission
→ workload classifier
├→ async I/O TaskRouter
└→ bounded ProcessPoolExecutor
→ response/error classification
```

Show retry and circuit breaker beside remote-call boundaries, not wrapped around the entire pipeline. Label overload, rate-limit and deadline outcomes.

- [ ] **Step 2: Render and write the phase page**

Render with `dot -Tsvg`. Map the diagram to `src/distsys/compute/`, `src/distsys/resilience/` and `src/distsys/node.py`. State that Phase 2 remains single-node.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/phase2-compute-resilience.md   docs/architecture/assets/phase2-architecture.*
git commit -m "docs: add phase 2 compute architecture"
```

---

### Task 4: Create Phase 3 distributed-cluster architecture

**Files:**
- Create: `docs/architecture/phase3-distributed-cluster.md`
- Create: `docs/architecture/assets/phase3-architecture.{mmd,dot,svg}`

**Interfaces:**
- Consumes: `src/distsys/cluster/` and node integration.
- Produces: cluster control-plane and routed-task topology.

- [ ] **Step 1: Model three bounded areas**

Use:

```text
Bootstrap: static seed → JOIN → membership merge
Failure detection: PING → indirect PING_REQ → SUSPECT → DEAD
Data routing: routing key → consistent-hash ring → owner → one-hop forward
```

Show gossip among three nodes, incarnation-aware state and deterministic candidate failover.

- [ ] **Step 2: State the boundary**

Include `best-effort/idempotent routing` and `not exactly once` in the page and diagram note.

- [ ] **Step 3: Render, validate and commit**

Use Graphviz to create the SVG, then:

```bash
git add docs/architecture/phase3-distributed-cluster.md   docs/architecture/assets/phase3-architecture.*
git commit -m "docs: add phase 3 cluster architecture"
```

---

### Task 5: Create Phase 4 causal CRDT architecture

**Files:**
- Create: `docs/architecture/phase4-causal-crdt.md`
- Create: `docs/architecture/assets/phase4-architecture.{mmd,dot,svg}`

**Interfaces:**
- Consumes: causal, CRDT, storage, replication, client and service packages.
- Produces: mutation, replication and convergence data-flow model.

- [ ] **Step 1: Model the causal operation flow**

Use:

```text
Client session token
→ causal validation
→ dotted mutation identity
→ local CRDT merge
→ RF=3 replica selection
→ asynchronous full-state replication
├→ targeted causal repair
└→ digest anti-entropy
→ converged replicas
```

List GCounter, PNCounter, ORSet and MVRegister inside the CRDT boundary.

- [ ] **Step 2: Add explicit non-guarantees**

The page must say no consensus, linearizability, quorum durability or distributed transactions.

- [ ] **Step 3: Render, validate and commit**

```bash
git add docs/architecture/phase4-causal-crdt.md   docs/architecture/assets/phase4-architecture.*
git commit -m "docs: add phase 4 causal crdt architecture"
```

---

### Task 6: Create Phase 5 secure persistence architecture

**Files:**
- Create: `docs/architecture/phase5-secure-persistence.md`
- Create: `docs/architecture/assets/phase5-architecture.{mmd,dot,svg}`

**Interfaces:**
- Consumes: persistence, recovery, coordination, security and health packages.
- Produces: durability, restart recovery and trust-boundary architecture.

- [ ] **Step 1: Model persistence and recovery**

Use:

```text
validated mutation
→ persistence admission
→ staged causal/CRDT state
→ SQLite WAL transaction
→ memory installation
→ async replication
→ ACK
```

Add restart flow:

```text
SQLite state → restore identity/frontier/entries
→ cluster join → stale-replica reconciliation → READY
```

Show etcd leases/discovery as coordination state and TLS 1.3/mTLS around every socket path.

- [ ] **Step 2: State local durability precisely**

The page must distinguish local durable ACK from quorum durability and etcd state from CRDT application state.

- [ ] **Step 3: Render, validate and commit**

```bash
git add docs/architecture/phase5-secure-persistence.md   docs/architecture/assets/phase5-architecture.*
git commit -m "docs: add phase 5 secure persistence architecture"
```

---

### Task 7: Normalize Phase 6 architecture

**Files:**
- Modify: `docs/architecture/phase6-observability-chaos-performance.md`
- Modify: `docs/architecture/assets/phase6-architecture.mmd`
- Modify: `docs/architecture/assets/phase6-architecture.dot`
- Regenerate: `docs/architecture/assets/phase6-architecture.svg`

**Interfaces:**
- Consumes: existing verified Phase 6 architecture.
- Produces: same semantics under the shared visual/status contract.

- [ ] **Step 1: Preserve all verified topology**

Retain three nodes, etcd, Toxiproxy, Prometheus, Grafana, OTel Collector, Tempo, benchmark driver, chaos controller, direct profile and proxy profile.

- [ ] **Step 2: Normalize presentation**

Add `IMPLEMENTED AND VERIFIED`, shared colors and source mappings. Preserve that healthy traffic bypasses proxies and chaos traffic explicitly opts in.

- [ ] **Step 3: Render and compare**

Run:

```bash
dot -Tsvg docs/architecture/assets/phase6-architecture.dot   -o docs/architecture/assets/phase6-architecture.svg
git diff -- docs/architecture/phase6-observability-chaos-performance.md   docs/architecture/assets/phase6-architecture.*
```

Confirm no behavior claim was added or removed.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture/phase6-observability-chaos-performance.md   docs/architecture/assets/phase6-architecture.*
git commit -m "docs: normalize phase 6 architecture"
```

---

### Task 8: Create planned Phase 7 production architecture

**Files:**
- Create: `docs/architecture/phase7-production-delivery.md`
- Create: `docs/architecture/assets/phase7-architecture.{mmd,dot,svg}`

**Interfaces:**
- Consumes: approved local-Kubernetes-first then AWS EKS direction.
- Produces: deployment target without claiming implementation.

- [ ] **Step 1: Model immutable artifact promotion**

Use:

```text
source commit
→ quality/security gates
→ immutable container image
→ local kind/k3d validation
→ Helm release contract
→ registry digest promotion
→ Terraform-provisioned AWS EKS
→ rollout verification / rollback
```

Include Kubernetes Deployment/StatefulSet decisions, Services, ConfigMaps, external secrets integration, ingress/load balancer, managed observability and explicit durable-state boundaries.

- [ ] **Step 2: Apply planned status**

Put `PLANNED — NOT IMPLEMENTED` in the page title area, Mermaid diagram, DOT diagram and rendered SVG.

- [ ] **Step 3: Render, scan and commit**

```bash
dot -Tsvg docs/architecture/assets/phase7-architecture.dot   -o docs/architecture/assets/phase7-architecture.svg
grep -F "PLANNED — NOT IMPLEMENTED"   docs/architecture/phase7-production-delivery.md   docs/architecture/assets/phase7-architecture.mmd   docs/architecture/assets/phase7-architecture.dot
git add docs/architecture/phase7-production-delivery.md   docs/architecture/assets/phase7-architecture.*
git commit -m "docs: add planned phase 7 architecture"
```

Expected: all three text files match the planned-status label.

---

### Task 9: Create the Phase 1–7 evolution overview

**Files:**
- Create: `docs/architecture/phase1-7-evolution.md`
- Create: `docs/architecture/assets/phase1-7-evolution.{mmd,dot,svg}`

**Interfaces:**
- Consumes: all seven phase architecture pages.
- Produces: recruiter-first cumulative progression.

- [ ] **Step 1: Model capability accumulation**

Use exactly seven phase nodes with these short labels:

```text
P1 Protocol
→ P2 Bounded execution
→ P3 Multi-node routing
→ P4 Causal replicated state
→ P5 Durable secure recovery
→ P6 Observable fault-tested runtime
→ P7 Planned production delivery
```

Show Phases 1–6 as implemented and Phase 7 as planned. Add a note that later phases preserve earlier guarantees.

- [ ] **Step 2: Write the overview page**

Include a capability matrix linking each phase to architecture, design and verification evidence where available.

- [ ] **Step 3: Render and commit**

```bash
git add docs/architecture/phase1-7-evolution.md   docs/architecture/assets/phase1-7-evolution.*
git commit -m "docs: add phase evolution architecture"
```

---

### Task 10: Integrate README and perform final verification

**Files:**
- Modify: `README.md`
- Verify: all `docs/architecture/**`
- Delete: `docs/design/phase1-7-architecture-implementation-plan.md`

**Interfaces:**
- Consumes: completed eight-diagram package.
- Produces: recruiter-facing navigation and clean final repository.

- [ ] **Step 1: Add concise README navigation**

Add one architecture subsection linking to:

- `docs/architecture/README.md`
- `docs/architecture/phase1-7-evolution.md`
- `docs/architecture/phase6-observability-chaos-performance.md`
- `docs/architecture/phase7-production-delivery.md`

Use `planned Phase 7 target` in the link text.

- [ ] **Step 2: Validate Graphviz sources and regenerate SVGs**

Run:

```bash
for source in docs/architecture/assets/*.dot
do
  dot -Tsvg "$source" -o "${source%.dot}.svg"
done
```

Expected: eight successful renders.

- [ ] **Step 3: Validate Mermaid sources**

Run:

```bash
for source in docs/architecture/assets/*.mmd
do
  npx -y @mermaid-js/mermaid-cli -i "$source" -o /tmp/"$(basename "${source%.mmd}").svg"
done
```

Expected: eight successful parses/renders. Temporary Mermaid renders are not committed.

- [ ] **Step 4: Validate relative Markdown links**

Run a Python link scanner over every tracked `.md` file. Resolve links relative to the source file, ignore HTTP(S), mailto and anchors, and fail if any resolved path is absent.

Expected: `markdown links: PASS`.

- [ ] **Step 5: Validate source mappings**

Extract every backticked `src/`, `scripts/` and `deploy/` mapping from the Phase 1–6 pages. Expand intentional directory references and fail if any mapped path is absent.

Expected: `architecture source mappings: PASS`.

- [ ] **Step 6: Validate status contracts**

Run:

```bash
grep -L "IMPLEMENTED AND VERIFIED" docs/architecture/phase[1-6]-*.md && exit 1 || true
grep -F "PLANNED — NOT IMPLEMENTED"   docs/architecture/phase7-production-delivery.md   docs/architecture/assets/phase7-architecture.mmd   docs/architecture/assets/phase7-architecture.dot
```

Expected: no Phase 1–6 page is missing its implemented status and all Phase 7 sources contain planned status.

- [ ] **Step 7: Remove the temporary plan**

```bash
git rm docs/design/phase1-7-architecture-implementation-plan.md
```

Keep `docs/design/phase1-7-architecture-package.md` as the durable design contract.

- [ ] **Step 8: Run repository quality checks**

```bash
python -m compileall -q src scripts tests
env -u RUN_CHAOS_TESTS -u RUN_PERFORMANCE_TESTS   -u PHASE6_PEER_PROXY_MAP make quality
```

Expected: pytest, Ruff, Black, mypy and compile checks pass.

- [ ] **Step 9: Confirm documentation-only diff**

```bash
git diff --name-only 9e3ef42..HEAD
```

Allowed paths:

```text
README.md
docs/architecture/**
docs/design/phase1-7-architecture-implementation-plan.md
```

No runtime, test, dependency, CI or deployment file may appear.

- [ ] **Step 10: Commit final integration**

```bash
git add README.md docs/architecture
git commit -m "docs: complete phase 1-7 architecture package"
```

- [ ] **Step 11: Verify remote state**

Push directly to `main`, wait for the Quality workflow, confirm `v0.6.0` resolves to its original annotated tag object, and report the complete commit sequence.
