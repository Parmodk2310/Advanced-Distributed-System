#!/usr/bin/env bash
set -euo pipefail
: "${GHCR_IMAGE:?set GHCR_IMAGE including @sha256 digest}"
: "${ECR_IMAGE:?set ECR_IMAGE destination repository:tag}"
[[ "$GHCR_IMAGE" == *@sha256:* ]] || { echo 'GHCR_IMAGE must be digest pinned' >&2; exit 2; }
command -v crane >/dev/null
source_digest="$(crane digest "$GHCR_IMAGE")"
crane copy "$GHCR_IMAGE" "$ECR_IMAGE"
target_digest="$(crane digest "$ECR_IMAGE")"
[[ "$source_digest" == "$target_digest" ]] || { echo 'registry digest mismatch' >&2; exit 1; }
printf '%s
' "$target_digest"
