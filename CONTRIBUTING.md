# Contributing

Thank you for considering a contribution to Advanced Distributed System.

This project prioritizes **correctness, explicit guarantees, reproducible
verification, and failure-safe operations** over feature count.

## Before you start

Read:

- [`README.md`](README.md)
- [`SECURITY.md`](SECURITY.md)
- [`docs/architecture/README.md`](docs/architecture/README.md)
- [`docs/verification/phase7.md`](docs/verification/phase7.md)

For security-sensitive findings, follow `SECURITY.md` rather than publishing
exploit details in a public issue.

## Development environment

Python 3.12 is required.

```bash
git clone https://github.com/Parmodk2310/Advanced-Distributed-System.git
cd Advanced-Distributed-System

python3.12 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

Deployment changes additionally require Docker, kind, kubectl, Helm, and
Terraform.

## Branches

Use focused branches from an up-to-date `main`.

Examples:

```text
feat/<short-description>
fix/<short-description>
docs/<short-description>
test/<short-description>
chore/<short-description>
```

For large phase work, a phase-scoped branch is acceptable.

Do not mix unrelated cleanup, refactors, feature changes, and documentation
changes in one PR unless they are necessary for one coherent outcome.

## Development workflow

For behavior changes:

1. Reproduce the current behavior or bug.
2. Add a focused failing test.
3. Verify the test fails for the intended reason.
4. Implement the smallest correct change.
5. Verify the focused test passes.
6. Run the broader relevant suite.
7. Update design/runbook/verification docs when guarantees or operational
   behavior change.

For documentation/configuration-only changes, keep edits minimal and validate
the relevant commands, schemas, and links.

## Quality gates

Run:

```bash
make quality
```

Equivalent core checks include:

```bash
python -m pytest -q
python -m ruff check src tests scripts
python -m black --check src tests scripts
python -m mypy src/distsys
python -m compileall -q src scripts tests
```

Deployment changes should also run:

```bash
python -m pytest tests/deployment -q
```

For changes affecting the local production-delivery path:

```bash
make phase7-release-gate
```

The local release gate must not create AWS resources.

## Distributed-system correctness expectations

A contribution that changes distributed behavior should document:

- safety property or invariant,
- liveness/recovery expectation,
- failure assumptions,
- persistence semantics,
- retry/idempotency behavior,
- ordering/causal assumptions,
- partition/peer-failure behavior,
- what the change still does **not** guarantee.

Avoid wording that accidentally upgrades the system's guarantees.

Claims such as these require explicit architecture and strong evidence:

- linearizability,
- consensus,
- quorum durability,
- exactly-once distributed execution,
- distributed ACID transactions,
- arbitrary fault tolerance.

## Tests

Prefer tests that exercise real behavior.

Useful categories:

- unit tests for pure algorithms/state,
- integration tests for multi-node behavior,
- contract tests for shell/Helm/Terraform/workflows,
- negative tests for malformed or untrusted inputs,
- recovery tests for restart/failure paths.

A regression test should fail before the fix and pass afterward.

## Performance changes

Do not optimize only for a benchmark number.

For performance-sensitive changes:

- preserve correctness checks,
- document the test profile,
- record environment metadata,
- use reproducible inputs/seeds,
- report p50/p95/p99 rather than only averages,
- avoid presenting local numbers as universal production capacity.

## Security changes

Consider:

- secret exposure,
- authentication vs. transport encryption,
- certificate identity,
- least privilege,
- non-root/container boundaries,
- network exposure,
- supply-chain provenance,
- teardown/cleanup behavior.

Never weaken a security gate just to make CI pass.

## Kubernetes / Helm changes

Verify:

- `helm lint`,
- rendering for relevant values files,
- kubeconform,
- Conftest/OPA policies,
- selector consistency,
- readiness/liveness behavior,
- StatefulSet/PVC identity where relevant,
- safe cleanup.

Do not expose a public `LoadBalancer` by default.

## Terraform / AWS changes

A PR may add or validate Terraform without creating cloud resources.

Actual apply should remain separately gated by:

- explicit workflow dispatch,
- deployment-enable variable,
- protected environment,
- exact source commit,
- reviewed plan,
- cost boundary,
- explicit approval.

Do not commit `.terraform/`, Terraform state, plan files, kubeconfigs, or
credentials.

## Commit style

Prefer clear conventional subjects:

```text
feat(cluster): add incarnation-aware rejoin
fix(storage): preserve causal counter across restart
test(phase7): cover rollback recovery
docs(release): add v0.7.0 evidence
chore(ci): update action runtime
```

## Pull requests

A strong PR includes:

- problem statement,
- solution summary,
- design trade-offs,
- verification commands/results,
- security/operational impact,
- explicit limitations/non-claims,
- screenshots or logs only when they add useful evidence.

Keep PRs reviewable.

## Documentation

Detailed phase design, runbooks, and evidence belong under `docs/`.

Keep the root README focused on the problem, architecture, verified outcomes,
quick start, major engineering decisions, and limitations.

## License

By intentionally contributing to this repository, you agree that your
contribution is submitted under the Apache License 2.0, consistent with the
repository license.
