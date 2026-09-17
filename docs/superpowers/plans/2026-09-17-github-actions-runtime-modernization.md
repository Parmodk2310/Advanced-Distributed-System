# GitHub Actions Node 24 Modernization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove GitHub-hosted runner Node 20 deprecation warnings using officially released Node 24-compatible action majors.

**Architecture:** Update only action runtime majors whose official release notes document Node 24 support. Keep tool versions and workflow behavior unchanged, verify contracts first, and require the same quality, image, Kubernetes, and Terraform gates.

**Tech Stack:** GitHub Actions, Python 3.12, Docker Buildx, Helm, kubectl, Terraform, AWS OIDC.

**Spec:** `docs/public-readiness-checklist.md`

## Global Constraints

- Keep `AWS_PHASE7_ENABLED=false`.
- Do not dispatch AWS plan or deploy workflows.
- Preserve all workflow inputs, permissions, conditions, concurrency, and pinned tool versions.
- Require official upstream release evidence for every changed action major.

---

### Task 1: Upgrade Node-runtime action majors

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/phase7-image-publish.yml`
- Modify: `.github/workflows/phase7-local-kubernetes.yml`
- Modify: `.github/workflows/phase7-aws-plan.yml`
- Modify: `.github/workflows/phase7-aws-deploy.yml`

- [ ] Replace `actions/checkout@v4` with `actions/checkout@v7`.
- [ ] Replace `actions/setup-python@v5` with `actions/setup-python@v7`.
- [ ] Replace `actions/upload-artifact@v4` with `actions/upload-artifact@v7`.
- [ ] Replace `aws-actions/configure-aws-credentials@v4` with `@v6`.
- [ ] Replace `azure/setup-helm@v4` with `@v5`.
- [ ] Replace `azure/setup-kubectl@v4` with `@v5`.
- [ ] Replace `docker/setup-buildx-action@v3` with `@v4`.
- [ ] Replace `hashicorp/setup-terraform@v3` with `@v4`.

### Task 2: Verify behavior

- [ ] Run deployment contract tests.
- [ ] Run `make quality`.
- [ ] Require Quality on the exact PR head.
- [ ] Require Phase 7 Local Kubernetes on the exact PR head.
- [ ] Require Phase 7 Image with Gitleaks, Trivy, SBOM, and kind verification.
- [ ] Confirm AWS workflows remain manual and gated.
- [ ] Squash-merge only after all triggered checks pass.
