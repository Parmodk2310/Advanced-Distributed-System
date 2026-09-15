# Phase 1–6 Repository Cleanup Design

## Purpose

Prepare the repository for recruiter and senior-engineer review before Phase 7. The cleanup removes obsolete delivery clutter, stabilizes documentation names, improves navigation, and adds structural safeguards without changing runtime behavior.

## Constraints

- Work directly on `main`; do not create a branch or pull request.
- Keep the repository private.
- Preserve the `v0.6.0` tag and all Git history.
- Do not modify Phase 1–6 runtime behavior.
- Do not remove source code, runtime configuration, tests, architecture figures, verification evidence, or benchmark methodology.
- Do not publish a GitHub Release or begin Phase 7.
- Use small, reviewable commits and verify after every structural change.

## Classification Rules

### Keep

Keep files that define or verify the product:

- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, project configuration, CI, and dependency files.
- `src/`, `tests/`, `scripts/`, `deploy/`, `docker/`, and runtime architecture.
- Phase verification records, architecture documentation, benchmark definitions, operational runbooks, and limitations.
- `src/distsys/recovery/` and its tests because recovery is a runtime subsystem, not delivery clutter.

### Delete from the current tree

Delete obsolete root-level application and hotfix instructions. Git history remains the authoritative archive:

- `APPLY_FINAL_HOTFIX.md`
- `APPLY_FINAL_WSL_HOTFIX.md`
- `APPLY_HOTFIX.md`
- `APPLY_PHASE2.md`
- `APPLY_PHASE3.md`
- `APPLY_PHASE4.md`
- `APPLY_PHASE5.md`
- `APPLY_PHASE5_RELEASE_GATE_FINAL_HOTFIX.md`
- `APPLY_PORT_HOTFIX.md`
- `APPLY_RELEASE_GATE_HOTFIX.md`
- `APPLY_STABILITY_HOTFIX.md`
- `APPLY_WSL_NETWORK_HOTFIX.md`

These files describe one-time delivery or repair procedures that no longer belong in the active product tree.

### Rename or relocate

- Remove calendar dates from active documentation filenames.
- Keep phase numbers where they communicate the product roadmap.
- Move superseded planning material under `docs/history/` only when it contains durable engineering rationale not already captured by architecture or verification documents.
- Prefer descriptive kebab-case names.
- Update every repository link in the same commit as a rename.
- Do not rename source files merely for stylistic consistency.

## Target Documentation Structure

The active documentation should have clear entry points:

- `README.md`: recruiter-first overview, verified proof points, architecture, quick start, limitations, and links.
- `docs/architecture/`: current architectural explanations and diagrams.
- `docs/verification/`: Phase 1–6 verification evidence with stable names.
- `docs/operations/`: runbooks, security, monitoring, chaos, and benchmark instructions.
- `docs/history/`: superseded plans retained only for design rationale.

The exact move map will be derived from reference analysis so that no live link or useful evidence is lost.

## Recruiter Experience

A reviewer should understand within one minute:

1. The problem: reliable distributed infrastructure for AI/ML services.
2. The system: three-node execution, causal CRDT replication, durable recovery, coordination, mTLS, observability, chaos testing, and performance gates.
3. The proof: test count, CI status, benchmark outcomes, and chaos recovery evidence.
4. Where to go next: architecture, verification, and source modules.

The README remains concise; deep implementation detail stays in linked documentation.

## Senior-Engineer Experience

A technical reviewer should be able to trace claims to:

- Architecture and correctness contracts.
- Source modules and integration boundaries.
- Phase-specific verification records.
- Reproducible commands and stated limitations.
- CI and local release-gate evidence.

Historical delivery mechanics must not compete with current design documentation.

## Structural Guard

Add a deterministic repository-policy check that fails when the active tree gains:

- Root-level `APPLY_*` or `*HOTFIX*` files.
- Committed ZIP bundles, generated logs, benchmark output, temporary archives, or cache artifacts.
- New dated active-documentation filenames outside `docs/history/`.

The guard must use an explicit allowlist for legitimate exceptions and run in the existing Python 3.12 Quality workflow.

## Verification

Before claiming completion:

1. Confirm the `v0.6.0` tag still resolves to its original commit.
2. Validate all Markdown links affected by moves or renames.
3. Run the repository-policy tests.
4. Run `python -m compileall -q src scripts tests`.
5. Run `make quality`.
6. Confirm the working tree represented by GitHub `main` contains no unintended deletions.
7. Confirm the GitHub Actions Quality workflow passes on the final commit.

The full Docker chaos and performance gate is not rerun unless a change touches runtime, scripts used by that gate, or release-gate configuration.

## Delivery

Use direct, small commits to `main`:

1. Record this design.
2. Remove obsolete root delivery files.
3. Normalize and reorganize documentation with repaired links.
4. Add the structural guard and tests.
5. Improve recruiter/senior-engineer navigation if the audit demonstrates a concrete gap.
6. Verify and report the final commit sequence.

No branch or pull request will be created.
