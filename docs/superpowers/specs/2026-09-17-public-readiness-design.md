# Public-Readiness and Recruiter-First Presentation Design

**Repository:** `Parmodk2310/Advanced-Distributed-System`  
**Branch:** `docs/recruiter-first-readme-release-license`  
**Status:** Approved design; implementation pending  
**Date:** 2026-09-17

## Purpose

Prepare the completed seven-phase distributed-system project for rigorous
evaluation by recruiters and senior engineers, while preserving precise
technical claims and keeping the repository private until a separate public
release decision.

The work improves presentation and open-source readiness. It does not change
runtime behavior, deploy cloud resources, publish a release, change repository
visibility, merge a pull request, rewrite history, or delete branches.

## Current-state findings

- The merged README is technically detailed but 583 lines long and weighted
  toward Phase 6 rather than the completed Phase 7 outcome.
- The problem, solution, verification evidence, and limitations are not all
  visible early enough for a recruiter scan.
- Five milestone tags exist, but there are no formal GitHub Releases.
- No `v0.5.0` tag exists and one must not be fabricated retroactively.
- GitHub currently detects no repository license.
- `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, and formal Phase 7
  release notes are absent from `main`.
- The repository is private and the AWS execution gate is disabled.
- Phase 7 evidence supports a temporary, reproducible apply-test-rollback-
  destroy lifecycle. It does not support claims of a permanently hosted,
  multi-AZ, production-HA service.

## Audience and success criteria

### Recruiter view

Within the first screen, a reader should understand:

1. the infrastructure problem,
2. why it matters to reliable AI/ML systems,
3. what was built,
4. the strongest verified outcome,
5. where to inspect or run it.

### Senior-engineer view

A technical reviewer should quickly find:

- explicit consistency and durability semantics,
- architecture and failure boundaries,
- important engineering trade-offs,
- reproducible verification and evidence,
- supply-chain and cloud-safety controls,
- accurate non-claims.

### Acceptance criteria

- README is materially shorter and easier to scan than the current version.
- Claims are traceable to committed evidence or green workflows.
- Quick-start commands match the repository.
- Mermaid and relative links render correctly on GitHub.
- Apache-2.0 is present and correctly referenced.
- Release documentation distinguishes tags, draft notes, and an actually
  published GitHub Release.
- Public-readiness checks explicitly cover full Git history, sensitive
  metadata, CI, cloud safety, branches, tags, and repository protection.
- No secret, private key, credential, Terraform state, plan file, kubeconfig,
  personal path, or unnecessary account metadata is added.

## Selected approach

Use a recruiter-first root README with progressive disclosure. Keep the root
focused on problem, solution, architecture, evidence, quick start, trade-offs,
and boundaries. Link detailed phase history, benchmarks, operations, and
verification to existing `docs/` material.

This is preferred over:

- retaining the phase-by-phase long-form README, which makes the final outcome
  difficult to scan; or
- replacing it with a marketing-only README, which would hide the correctness
  boundaries that make the project credible to senior engineers.

## Planned files

### `README.md`

Rewrite around this order:

1. concise value proposition and workflow-backed badges,
2. problem and why it is difficult,
3. implemented solution,
4. verified outcome,
5. compact system and delivery architecture,
6. engineering decisions and trade-offs,
7. capabilities and tested failure scenarios,
8. local quick start,
9. immutable release identity and evidence links,
10. phase progression and repository map,
11. limitations/non-claims,
12. releases, security, contributing, and license.

Avoid decorative badges that merely restate claims. A badge may represent a
workflow, a real technology requirement, or the detected license, but must not
substitute for evidence.

### `LICENSE`

Add the unmodified Apache License 2.0 text with the project copyright notice.
Apache-2.0 is selected for its permissive commercial use and explicit patent
grant. The repository license does not relicense third-party dependencies,
services, or trademarks.

### `CHANGELOG.md`

Document historical tags as engineering milestones, record Phase 5 without
inventing `v0.5.0`, and keep `v0.7.0` under an unreleased/planned heading until
the formal release exists.

### `SECURITY.md`

Define supported-version expectations, responsible reporting, response scope,
credential hygiene, cloud-safety expectations, dependency/image controls, and
explicit security non-claims. Do not publish a private email address unless the
owner deliberately chooses to do so; prefer GitHub private vulnerability
reporting when enabled.

### `CONTRIBUTING.md`

Explain local setup, focused branches/PRs, quality gates, distributed-system
correctness expectations, testing, performance evidence, Kubernetes/Terraform
safety, and Apache-2.0 contribution terms.

### `docs/releases/v0.7.0.md`

Keep this as draft release notes until publication. Record the verified source
commit and immutable digests, verified lifecycle, limitations, local
verification commands, and the historical missing-tag note. Revalidate every
identifier before publishing the release.

### `docs/public-readiness-checklist.md`

Provide a strict go/no-go checklist for ownership, full-history secret scan,
sensitive metadata, presentation, policy files, CI/supply chain, AWS safety,
branch/tag hygiene, main protection, formal release, visibility change, and
post-publication review.

## Claim and evidence policy

- Use “verified” only for behavior supported by recorded evidence or successful
  workflow output.
- Keep `435 passed, 8 skipped` where the underlying run records both values;
  do not shorten it in a way that hides skipped tests.
- Describe the AWS environment as temporary and destroyed.
- Describe the demonstrated EKS topology as one worker, not HA.
- Do not claim consensus, linearizability, quorum durability, exactly-once
  distributed execution, distributed ACID transactions, production SLOs,
  internet-scale capacity, or multi-region recovery.
- Distinguish an immutable image digest from an image signature and from a
  workflow artifact digest.
- Do not call `v0.7.0` released until the tag and GitHub Release exist.

## Verification strategy

The documentation PR will run:

1. Markdown and relative-link checks,
2. duplicate/broken-anchor inspection,
3. Mermaid syntax/render sanity review,
4. secret and sensitive-metadata scans over the changed files,
5. repository quality checks,
6. deployment documentation/contract tests,
7. exact-branch GitHub Actions checks.

The full local Kubernetes gate will run if the README or policy changes affect
commands/contracts consumed by Phase 7 tests. No AWS workflow will be enabled
or dispatched for this documentation change.

## Release and publication sequence

1. Implement and review this documentation set on the dedicated branch.
2. Open a pull request while the repository remains private.
3. Require green checks and review the rendered README.
4. Merge only after explicit approval.
5. Revalidate the exact `main` release commit and all recorded digests.
6. Create `v0.7.0` as the first formal GitHub Release only with separate
   approval.
7. Complete the public-readiness checklist and branch/ruleset review.
8. Change visibility to public only with separate explicit approval.

## Out of scope

- Runtime or protocol changes
- New benchmarks or revised performance numbers
- AWS apply/destroy execution
- Repository visibility change
- GitHub Release publication
- Tag creation
- Branch deletion or history rewriting
- Pull-request merge
