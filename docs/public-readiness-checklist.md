# Public Repository Readiness Checklist

Use this checklist before changing
`Parmodk2310/Advanced-Distributed-System` from private to public.

This checklist is intentionally not marked complete in advance. Each item must
be verified against the exact commit that will be published.

Making a repository public can expose its full reachable Git history, not only
the current working tree.

## Audit record — 2026-09-17

- Repository visibility at audit start: **private**.
- Default branch: `main`.
- `backup/main-before-phase1` has no common ancestor with `main`; preserve it
  until its unrelated history is inspected separately.
- `chore/phase1-5-repository-hardening` and
  `docs/phase7-verification-complete` contain commits not reachable from
  `main`; preserve them.
- The phase branches and lifecycle hotfix branches compared as ancestors of
  `main`; no deletion is performed in this release-preparation change.
- `docs/public-release-readiness` and
  `docs/recruiter-first-readme-release-license` are completed documentation
  branches whose changes were squash-merged; their deletion was separately
  approved.
- Full-history Gitleaks, image scanning, SBOM, signature, and local Kubernetes
  checks remain mandatory GitHub workflow gates for the exact release
  candidate. This record does not pre-mark those checks as passed.

## 1. Ownership and licensing

- [ ] Confirm ownership/permission for all first-party source, docs, diagrams,
      examples, and test data.
- [ ] Confirm no employer/client/internship confidential code was copied in.
- [ ] Add `LICENSE`.
- [ ] Confirm GitHub detects `Apache-2.0`.
- [ ] Confirm third-party names/logos are used only descriptively.
- [ ] Do not imply your license relicenses Kubernetes, etcd, Terraform, Docker,
      AWS, Prometheus, Grafana, OpenTelemetry, or dependencies.

## 2. Full-history secret scan

A current-tree scan is not enough.

```bash
git fetch --all --tags --prune
git rev-parse --is-shallow-repository
```

The result should be `false`.

Then run the repository's approved Gitleaks full-history scan.

- [ ] full history available
- [ ] branches/tags intended to remain reachable scanned
- [ ] no AWS keys
- [ ] no GitHub tokens
- [ ] no private keys
- [ ] no passwords
- [ ] no API keys
- [ ] no credentials hidden in old patches
- [ ] any previously exposed secret revoked, not merely deleted

If a live secret ever existed in history, rotate/revoke it first. History
rewriting is a separate high-risk operation and should not be done casually.

## 3. Sensitive metadata audit

Search current tree and relevant history for:

- [ ] AWS account IDs
- [ ] unnecessary ARNs
- [ ] IP addresses that should not be permanent documentation
- [ ] personal email addresses
- [ ] local absolute paths
- [ ] Windows user paths
- [ ] kubeconfig content
- [ ] Terraform state
- [ ] Terraform plan files
- [ ] real `.env` values
- [ ] TLS private keys
- [ ] certificates with unnecessary personal/internal identifiers
- [ ] screenshots/logs with billing or account information

## 4. Repository presentation

- [ ] recruiter-first README merged
- [ ] problem visible within first screen
- [ ] architecture understandable without reading phase history
- [ ] verified outcomes visible quickly
- [ ] quick start works
- [ ] non-claims explicit
- [ ] detailed history kept under `docs/`
- [ ] description concise
- [ ] topics relevant
- [ ] broken links checked

Suggested description:

> Correctness-first distributed infrastructure for reliable AI/ML services:
> causal CRDTs, durable state, mTLS, observability, chaos testing, Kubernetes,
> Terraform, and verified AWS delivery.

Suggested topics:

```text
distributed-systems
python
asyncio
crdt
causal-consistency
consistent-hashing
swim
etcd
mtls
reliability-engineering
chaos-engineering
opentelemetry
prometheus
grafana
docker
kubernetes
helm
terraform
aws
```

## 5. Policy files

- [ ] `LICENSE` present
- [ ] `SECURITY.md` reviewed
- [ ] private vulnerability reporting enabled if available
- [ ] `CONTRIBUTING.md` reviewed
- [ ] `CHANGELOG.md` reviewed
- [ ] no contact information exposed unintentionally

## 6. CI and supply chain

Before public visibility:

- [ ] Quality workflow green on exact presentation commit
- [ ] Phase 7 local Kubernetes workflow green
- [ ] Image workflow green
- [ ] Gitleaks green
- [ ] Trivy gate green
- [ ] SBOM generated
- [ ] immutable image digest recorded
- [ ] keyless signature verified where applicable
- [ ] Node/runtime deprecation warnings reviewed
- [ ] no CI step depends on a private-only assumption

## 7. Cloud safety

- [ ] `AWS_PHASE7_ENABLED=false`
- [ ] no AWS deployment triggered by push/PR alone
- [ ] AWS workflows remain manual/protected
- [ ] no long-lived AWS credentials in repo files/settings
- [ ] OIDC role trust reviewed
- [ ] Terraform state backend intentionally separate
- [ ] no demo load balancer remains
- [ ] no EKS cluster remains
- [ ] no demo ECR repository remains unless intentionally retained
- [ ] no demo EBS volumes remain
- [ ] no demo VPC/network resources remain
- [ ] residual-resource verification recorded

## 8. Branch and tag hygiene

- [ ] list local and remote branches
- [ ] verify merged branches contain no unique work before deletion
- [ ] delete stale merged branches you no longer need
- [ ] keep branches with unique historical work until reviewed
- [ ] do not force-delete unknown branches
- [ ] review all tags
- [ ] keep intentional historical milestone tags
- [ ] do **not** manufacture `v0.5.0`
- [ ] confirm the commit intended for `v0.7.0`

## 9. Main-branch protection

Recommended baseline for a single-maintainer portfolio repo:

- [ ] require pull request before merge
- [ ] require key CI checks
- [ ] block force pushes to `main`
- [ ] block deletion of `main`
- [ ] require conversation resolution where useful
- [ ] keep admin override only if you understand the trade-off

Avoid process theater: one maintainer does not need fake multi-reviewer
approval.

## 10. Release preparation

- [ ] merge the presentation/public-readiness PR
- [ ] rerun CI on exact release commit
- [ ] confirm `docs/verification/phase7.md`
- [ ] confirm release notes match real behavior
- [ ] confirm exact source commit
- [ ] confirm image digest
- [ ] confirm SBOM digest
- [ ] confirm Apache-2.0 license present

Then create:

```text
Tag:   v0.7.0
Title: v0.7.0 — Verified Kubernetes and AWS Delivery Lifecycle
```

Use [`docs/releases/v0.7.0.md`](releases/v0.7.0.md) as the release body.

## 11. Visibility-change decision

Only after all earlier sections are complete:

- [ ] take a final backup/clone
- [ ] verify `main` clean and synchronized
- [ ] verify no unexpected open PR contains sensitive history
- [ ] verify no pending workflow can create AWS resources
- [ ] confirm AWS execution gate disabled
- [ ] change repository visibility to **public**

Do not combine visibility change with unrelated code changes.

## 12. Post-publication checks

Immediately after making the repository public:

- [ ] open the repo logged-out/incognito
- [ ] verify README rendering
- [ ] verify Mermaid rendering
- [ ] verify badges
- [ ] verify license detection
- [ ] verify release page
- [ ] verify documentation links
- [ ] verify no sensitive artifact is visible
- [ ] verify Actions permissions remain appropriate
- [ ] verify no workflow unexpectedly runs AWS deployment
- [ ] verify repository description/topics

## Go / no-go rule

**GO PUBLIC** only when:

```text
ownership confirmed
+ Apache-2.0 present
+ full-history secret scan clean
+ sensitive metadata audit clean
+ CI green
+ cloud gate disabled
+ teardown verified
+ branch/tag review complete
+ release notes reviewed
```

Otherwise keep the repository private.
