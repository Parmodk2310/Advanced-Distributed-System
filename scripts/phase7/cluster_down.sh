#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

require_tool kind

if kind get clusters 2>/dev/null | grep -Fxq "$PHASE7_CLUSTER_NAME"; then
  kind delete cluster --name "$PHASE7_CLUSTER_NAME"
fi

safe_remove_dir "$PHASE7_TLS_DIR"
rmdir "$PHASE7_WORK_DIR" 2>/dev/null || true
echo "Phase 7 local resources removed."
