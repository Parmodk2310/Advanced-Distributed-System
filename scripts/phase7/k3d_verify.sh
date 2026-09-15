#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

if ! command -v k3d >/dev/null 2>&1; then
  printf 'k3d is not installed; optional parity check skipped\n'
  exit 0
fi
for required in docker kubectl helm openssl; do
  phase7_require_command "$required"
done
phase7_prepare_work_dir

cleanup() {
  k3d cluster delete "$PHASE7_K3D_CLUSTER" >/dev/null 2>&1 || true
  rm -rf "$PHASE7_WORK_DIR"
}
trap cleanup EXIT INT TERM

docker build --pull --tag "$PHASE7_IMAGE" "$PHASE7_REPO_ROOT"
k3d cluster create --config "$PHASE7_REPO_ROOT/deploy/k3d/cluster.yaml"
k3d image import --cluster "$PHASE7_K3D_CLUSTER" "$PHASE7_IMAGE"
kubectl create namespace "$PHASE7_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$PHASE7_REPO_ROOT/deploy/kind/etcd.yaml"
kubectl -n "$PHASE7_NAMESPACE" rollout status deployment/etcd --timeout=120s
"$PHASE7_SCRIPT_DIR/generate_tls_secret.sh"
helm upgrade --install "$PHASE7_RELEASE" "$(phase7_chart_dir)" \
  --namespace "$PHASE7_NAMESPACE" \
  --values "$(phase7_chart_dir)/values-kind.yaml" \
  --set image.repository="${PHASE7_IMAGE%%:*}" \
  --set image.tag="${PHASE7_IMAGE##*:}" \
  --wait --timeout 5m
kubectl -n "$PHASE7_NAMESPACE" rollout status \
  "statefulset/$PHASE7_RELEASE-distributed-system" --timeout=180s
printf 'optional k3d parity check passed\n'
