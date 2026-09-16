#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
phase7_require_command kubectl; phase7_require_command helm
kubectl -n "$PHASE7_NAMESPACE" rollout status "statefulset/$PHASE7_ETCD_RELEASE" --timeout=5m
members="$(kubectl -n "$PHASE7_NAMESPACE" get pods -l app.kubernetes.io/name=etcd,app.kubernetes.io/instance="$PHASE7_ETCD_RELEASE" --field-selector=status.phase=Running -o name | wc -l)"
[[ "$members" == 3 ]] || { printf 'expected 3 running etcd members, got %s
' "$members" >&2; exit 1; }
kubectl -n "$PHASE7_NAMESPACE" rollout status "statefulset/$PHASE7_RELEASE-distributed-system" --timeout=5m
PYTHONPATH="$PHASE7_REPO_ROOT/src" python "$PHASE7_SCRIPT_DIR/verify_cluster.py" --namespace "$PHASE7_NAMESPACE" --release "$PHASE7_RELEASE" --work-dir "$PHASE7_WORK_DIR" --output "$PHASE7_WORK_DIR/evidence/eks-private.json"
