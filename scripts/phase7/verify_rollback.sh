#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
phase7_require_command helm; phase7_require_command kubectl
revision="$(helm -n "$PHASE7_NAMESPACE" history "$PHASE7_RELEASE" -o json | python -c 'import json,sys; print(json.load(sys.stdin)[-1]["revision"])')"
if helm upgrade "$PHASE7_RELEASE" "$(phase7_chart_dir)" --namespace "$PHASE7_NAMESPACE" --reuse-values --set-string probes.readinessPath=/health/phase7-intentional-failure --wait --timeout 30s; then
  echo 'expected deliberately unhealthy upgrade to fail' >&2; exit 1
fi
helm rollback "$PHASE7_RELEASE" "$revision" --namespace "$PHASE7_NAMESPACE" --timeout "$PHASE7_HELM_TIMEOUT"
kubectl -n "$PHASE7_NAMESPACE" delete "pod/$PHASE7_RELEASE-distributed-system-2" --wait=false
kubectl -n "$PHASE7_NAMESPACE" rollout status "statefulset/$PHASE7_RELEASE-distributed-system" --timeout="$PHASE7_HELM_TIMEOUT"
PYTHONPATH="$PHASE7_REPO_ROOT/src" python "$PHASE7_SCRIPT_DIR/verify_cluster.py" --namespace "$PHASE7_NAMESPACE" --release "$PHASE7_RELEASE" --work-dir "$PHASE7_WORK_DIR" --output "$PHASE7_WORK_DIR/evidence/rollback.json"
