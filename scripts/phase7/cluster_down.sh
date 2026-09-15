#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

phase7_validate_work_dir

if command -v kind >/dev/null 2>&1; then
  kind delete cluster --name "$PHASE7_KIND_CLUSTER" >/dev/null 2>&1 || true
fi
if command -v k3d >/dev/null 2>&1; then
  k3d cluster delete "$PHASE7_K3D_CLUSTER" >/dev/null 2>&1 || true
fi

rm -rf "$PHASE7_WORK_DIR"
printf 'Phase 7 local clusters and ephemeral workspace removed\n'
