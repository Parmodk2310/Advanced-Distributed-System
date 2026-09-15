#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

for required in docker kind kubectl helm openssl; do
  phase7_require_command "$required"
done
phase7_prepare_work_dir

cleanup_required=1
print_failure_diagnostics() {
  if ! kubectl get namespace "$PHASE7_NAMESPACE" >/dev/null 2>&1; then
    return
  fi
  printf '%s\n' '--- Phase 7 failure diagnostics: resources ---' >&2
  timeout 20s kubectl -n "$PHASE7_NAMESPACE" get pods,pvc,svc,statefulset,events >&2 || true
  printf '%s\n' '--- Phase 7 failure diagnostics: pod descriptions ---' >&2
  timeout 20s kubectl -n "$PHASE7_NAMESPACE" describe pods >&2 || true
  printf '%s\n' '--- Phase 7 failure diagnostics: node logs ---' >&2
  while IFS= read -r pod; do
    timeout 10s kubectl -n "$PHASE7_NAMESPACE" logs "$pod" \
      --all-containers --prefix --tail=100 >&2 || true
    timeout 10s kubectl -n "$PHASE7_NAMESPACE" logs "$pod" \
      --container node --previous --prefix --tail=100 >&2 || true
  done < <(
    kubectl -n "$PHASE7_NAMESPACE" get pods \
      --selector app.kubernetes.io/instance="$PHASE7_RELEASE",app.kubernetes.io/name=distributed-system \
      --output name 2>/dev/null || true
  )
}

cleanup_on_exit() {
  if [[ "$cleanup_required" == "1" ]]; then
    print_failure_diagnostics
    "$PHASE7_SCRIPT_DIR/cluster_down.sh"
  fi
}
trap cleanup_on_exit EXIT INT TERM

if [[ "${PHASE7_SKIP_BUILD:-0}" != "1" ]]; then
  docker build --pull --tag "$PHASE7_IMAGE" "$PHASE7_REPO_ROOT"
fi
kind create cluster --config "$PHASE7_REPO_ROOT/deploy/kind/cluster.yaml"
kind load docker-image --name "$PHASE7_KIND_CLUSTER" "$PHASE7_IMAGE"

kubectl create namespace "$PHASE7_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$PHASE7_REPO_ROOT/deploy/kind/etcd.yaml"
kubectl -n "$PHASE7_NAMESPACE" rollout status deployment/etcd --timeout=120s
"$PHASE7_SCRIPT_DIR/generate_tls_secret.sh"

helm upgrade --install "$PHASE7_RELEASE" "$(phase7_chart_dir)" \
  --namespace "$PHASE7_NAMESPACE" \
  --values "$(phase7_chart_dir)/values-kind.yaml" \
  --set image.repository="${PHASE7_IMAGE%%:*}" \
  --set image.tag="${PHASE7_IMAGE##*:}" \
  --wait --timeout "$PHASE7_HELM_TIMEOUT"

kubectl -n "$PHASE7_NAMESPACE" rollout status \
  "statefulset/$PHASE7_RELEASE-distributed-system" --timeout=180s

cleanup_required=0
printf 'Phase 7 kind cluster is ready\n'
