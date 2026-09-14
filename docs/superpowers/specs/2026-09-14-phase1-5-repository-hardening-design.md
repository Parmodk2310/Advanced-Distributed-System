# Phase 1–5 Repository Hardening Design

## Status

Approved direction: evidence-first, non-destructive repository hardening on `chore/phase1-5-repository-hardening` while Phase 6 continues independently on `phase/6-observability-chaos`.

## Goal

Make the completed Phase 1–5 work understandable within 30 seconds to a recruiter and credible under detailed review by a senior engineer, without changing distributed-system runtime behavior or publishing the private repository.

## Positioning

Lead with **distributed infrastructure for reliable AI/ML services**. The repository remains technically accurate as a distributed-systems project; it does not claim to train, evaluate, or serve an ML model. Secondary positioning is backend, platform, and distributed-systems engineering.

Primary one-sentence message:

> A correctness-first distributed infrastructure platform built in Python to demonstrate how reliable AI/ML services can route work, replicate causal state, survive failures, recover durable data, and authenticate peers securely.

## Scope

### Included

- Rewrite the README opening and navigation for recruiter-first scanning and senior-engineer depth.
- Preserve existing durability, causal-consistency, security, recovery, and non-goal explanations.
- Add a rendered Phase 1–5 architecture asset and a source-controlled Mermaid source.
- Add GitHub Actions for Python 3.12, pytest, Ruff, Black, mypy, and compile checks.
- Add workflow and verification badges whose URLs target `main`.
- Add `CONTRIBUTING.md`, `SECURITY.md`, and a Phase 1–5 architecture document.
- Move root hotfix explanations to `docs/history/hotfixes/` using Git moves so history remains traceable.
- Add a concise verification summary and feature matrix based only on recorded evidence.
- Recommend repository description and topics in a copy-paste metadata document because repository metadata is not source-controlled.
- Verify documentation links, YAML syntax, Python quality gates, and the full existing test suite.

### Excluded

- Changing repository visibility.
- Deleting any local or remote branch.
- Rewriting or squashing Git history.
- Adding a license.
- Creating tags or GitHub releases.
- Publishing, deploying, or creating GitHub Pages.
- Merging into `main`.
- Modifying Phase 1–5 runtime behavior, protocol schemas, consistency guarantees, dependencies, or production configuration.
- Adding Phase 6 code to this branch.

## Branch Isolation

`chore/phase1-5-repository-hardening` starts at Phase 5 `main` commit `3fb542e6804ac0e2cb75b46dbe2d05508ae8dff3`. It must not merge or cherry-pick the Phase 6 branch. If Phase 6 later changes README or CI, those conflicts are resolved when the hardening branch is deliberately integrated, not during this task.

## README Information Architecture

The README order becomes:

1. title, concise value proposition, and CI badges;
2. recruiter-oriented `Why this project` and `Engineering evidence` table;
3. rendered architecture figure;
4. capabilities grouped by reliability, consistency, durability, coordination, and security;
5. five-minute local setup and one-command verification;
6. exact guarantees and explicit non-guarantees;
7. detailed Phase 5 durability/restart explanation;
8. source layout, documentation index, and roadmap.

Claims must be backed by files or recorded verification. The README may say `303 passed, 3 skipped` only as a dated Phase 5 recorded result and must link to `docs/PHASE5_VERIFICATION.md`. It must not present that result as a fresh CI run until CI produces it.

## Architecture Asset

Create:

- `docs/architecture/phase1-5-architecture.mmd` as the editable Mermaid source;
- `docs/architecture/phase1-5-architecture.svg` as the rendered GitHub asset;
- `docs/architecture/PHASE1_TO_PHASE5.md` as the explanation of boundaries and data flows.

The figure shows clients, three mTLS nodes, task routing, SWIM membership, causal CRDT replication, SQLite/WAL, recovery, anti-entropy, and etcd discovery/leases. It distinguishes data-plane responsibilities from coordination and explicitly labels local durability rather than quorum durability.

No secrets, host-specific paths, live IPs, or generated certificate material appear in the figure.

## CI Design

Create `.github/workflows/quality.yml` triggered by pull requests, pushes to `main`, and manual dispatch.

One Python 3.12 job will:

1. check out the repository;
2. install `.[dev]` with pip caching;
3. run `python -m pytest -q`;
4. run `python -m ruff check src tests scripts`;
5. run `python -m black --check src tests scripts`;
6. run `python -m mypy src/distsys`;
7. run `python -m compileall -q src scripts tests`;
8. run `bash -n` against every tracked shell script.

The workflow does not run Docker, real-etcd, mTLS smoke, Phase 6 chaos, or performance tests. Those remain explicit local gates because hosted-runner timing and container behavior would make the base quality signal noisy. Workflow permissions are `contents: read`; dependency actions use immutable major-version tags already supported by the repository's current workflow conventions.

## Repository Documents

### `CONTRIBUTING.md`

Describe environment setup, branch naming, test-first expectations, protobuf regeneration, quality commands, commit conventions, generated-artifact exclusions, and pull-request evidence. Do not suggest bypassing tests or committing generated secrets/runtime state.

### `SECURITY.md`

Document private vulnerability reporting guidance without inventing an email address. Ask reporters to use GitHub private vulnerability reporting when enabled or contact the repository owner privately through the GitHub profile. State supported version as the current `main` branch until releases exist. Clearly label development certificates as non-production.

### Verification summary and feature matrix

Create `docs/PHASE1_TO_PHASE5_SUMMARY.md` containing:

- one row per phase with capability, main components, verification evidence, and limitation;
- a feature matrix covering protocol, execution, membership, routing, CRDTs, causal consistency, persistence, coordination, mTLS, recovery, observability status, chaos status, and deployment status;
- exact links to the existing phase manifests and verification reports;
- no invented benchmark numbers.

### Metadata recommendation

Create `docs/REPOSITORY_METADATA.md` with the approved description and topics. It is advisory only; this task does not change GitHub visibility, settings, or metadata automatically.

## Hotfix Documentation Organization

Move the following tracked root documents under `docs/history/hotfixes/` when present:

- `APPLY_FINAL_HOTFIX.md`
- `APPLY_FINAL_WSL_HOTFIX.md`
- `APPLY_HOTFIX.md`
- `APPLY_PHASE5_RELEASE_GATE_FINAL_HOTFIX.md`
- `APPLY_PORT_HOTFIX.md`
- `APPLY_RELEASE_GATE_HOTFIX.md`
- `APPLY_STABILITY_HOTFIX.md`
- `APPLY_WSL_NETWORK_HOTFIX.md`

Retain `APPLY_PHASE2.md`, `APPLY_PHASE3.md`, `APPLY_PHASE4.md`, and `APPLY_PHASE5.md` as phase application guides unless link analysis shows they are purely historical. Add `docs/history/hotfixes/README.md` explaining that the files are retained as engineering history and are not current installation instructions.

All internal links must be updated. Files are moved, not copied and deleted independently, so Git can detect renames and preserve blame/history navigation.

## Verification and Error Handling

The hardening branch must pass:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check src tests scripts
python -m black --check src tests scripts
python -m mypy src/distsys
python -m compileall -q src scripts tests
for file in scripts/*.sh; do bash -n "$file"; done
```

Additional repository checks verify:

- every relative Markdown link resolves;
- the workflow parses as YAML;
- badges target the correct repository and `main` workflow;
- README claims match recorded evidence;
- the SVG contains no external scripts or links;
- root hotfix files are absent and destination files exist;
- no runtime source, protocol, requirements, generated protobuf, or test behavior changed;
- no key, certificate, environment secret, database, log, or benchmark artifact is newly tracked.

If the baseline test suite fails before hardening changes, stop implementation and report the baseline failure. Documentation or CI changes must never be used to hide or weaken a failing gate.

## Acceptance Criteria

1. A recruiter can identify purpose, target role relevance, core capabilities, and verified evidence from the first README screen.
2. A senior engineer can reach consistency, durability, recovery, security, architecture, and verification details without lost information.
3. The architecture image renders in GitHub and its Mermaid source is editable.
4. GitHub Actions covers the complete non-Docker quality gate with least-privilege permissions.
5. README badges point to real workflow/status URLs.
6. Contribution and security guidance are accurate and do not invent contact information or support promises.
7. Historical hotfix notes are organized and all repository links remain valid.
8. Phase 1–5 evidence is concise, linked, and free of unsupported performance claims.
9. Runtime behavior and source implementation are unchanged.
10. The repository stays private, branches remain intact, no license/release/tag is created, and nothing is merged to `main`.

