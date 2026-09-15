#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
phase7_require_command helm
phase7_require_command kubectl

readonly revision="$(helm -n "$PHASE7_NAMESPACE" history "$PHASE7_RELEASE" -o json | \
  python -c 'import json,sys; print(json.load(sys.stdin)[-1]["revision"])')"

if helm upgrade "$PHASE7_RELEASE" "$(phase7_chart_dir)" \
  --namespace "$PHASE7_NAMESPACE" --reuse-values \
  --set-string image.tag=missing-phase7-rollback-image \
  --wait --timeout 30s; then
  printf '%s\n' 'expected deliberately unhealthy upgrade to fail' >&2
  exit 1
fi

helm rollback "$PHASE7_RELEASE" "$revision" \
  --namespace "$PHASE7_NAMESPACE" --wait --timeout "$PHASE7_HELM_TIMEOUT"
PYTHONPATH="$PHASE7_REPO_ROOT/src" python "$PHASE7_SCRIPT_DIR/verify_cluster.py" \
  --namespace "$PHASE7_NAMESPACE" --release "$PHASE7_RELEASE" \
  --work-dir "$PHASE7_WORK_DIR" \
  --output "$PHASE7_WORK_DIR/evidence/rollback.json"
