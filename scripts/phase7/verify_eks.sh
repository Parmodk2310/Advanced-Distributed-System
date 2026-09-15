#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
kubectl -n "$PHASE7_NAMESPACE" rollout status "statefulset/$PHASE7_RELEASE-distributed-system" --timeout=5m
PYTHONPATH="$PHASE7_REPO_ROOT/src" python "$PHASE7_SCRIPT_DIR/verify_cluster.py" \
  --namespace "$PHASE7_NAMESPACE" --release "$PHASE7_RELEASE" --work-dir "$PHASE7_WORK_DIR"
