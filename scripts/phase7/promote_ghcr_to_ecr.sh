#!/usr/bin/env bash
set -euo pipefail
: "${GHCR_IMAGE:?set GHCR_IMAGE including @sha256 digest}"
: "${ECR_IMAGE:?set ECR_IMAGE including repository and digest tag}"
[[ "$GHCR_IMAGE" == *@sha256:* ]] || { printf '%s\n' 'GHCR_IMAGE must be digest pinned' >&2; exit 2; }
command -v crane >/dev/null
crane copy "$GHCR_IMAGE" "$ECR_IMAGE"
source_digest="$(crane digest "$GHCR_IMAGE")"
target_digest="$(crane digest "$ECR_IMAGE")"
[[ "$source_digest" == "$target_digest" ]] || { printf '%s\n' 'registry digest mismatch' >&2; exit 1; }
printf 'verified digest: %s\n' "$source_digest"
