#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
phase7_validate_work_dir
command -v kind >/dev/null 2>&1 && kind delete cluster --name "$PHASE7_KIND_CLUSTER" >/dev/null 2>&1 || true
command -v k3d >/dev/null 2>&1 && k3d cluster delete "$PHASE7_K3D_CLUSTER" >/dev/null 2>&1 || true
rm -rf "$PHASE7_WORK_DIR"
printf 'Phase 7 local clusters and ephemeral workspace removed
'
