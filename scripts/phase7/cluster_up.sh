#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

cleanup_on_error() {
  local status=$?
  echo "Phase 7 startup failed; removing the isolated cluster." >&2
  "$PHASE7_SCRIPT_DIR/cluster_down.sh" || true
  exit "$status"
}
trap cleanup_on_error ERR INT TERM

for tool in docker kind kubectl helm openssl; do
  require_tool "$tool"
done

if kind get clusters 2>/dev/null | grep -Fxq "$PHASE7_CLUSTER_NAME"; then
  echo "cluster already exists: $PHASE7_CLUSTER_NAME" >&2
  exit 2
fi

docker build --pull --tag "$PHASE7_IMAGE" "$PHASE7_REPO_ROOT"
kind create cluster   --name "$PHASE7_CLUSTER_NAME"   --config "$PHASE7_REPO_ROOT/deploy/kind/cluster.yaml"   --wait 120s
kind load docker-image "$PHASE7_IMAGE" --name "$PHASE7_CLUSTER_NAME"

kubectl create namespace "$PHASE7_NAMESPACE"
kubectl label namespace "$PHASE7_NAMESPACE"   kubernetes.io/metadata.name="$PHASE7_NAMESPACE" --overwrite
kubectl -n "$PHASE7_NAMESPACE" apply -f "$PHASE7_REPO_ROOT/deploy/kind/etcd.yaml"
kubectl -n "$PHASE7_NAMESPACE" rollout status deployment/etcd --timeout=120s

"$PHASE7_SCRIPT_DIR/generate_tls_secret.sh"

helm upgrade --install "$PHASE7_RELEASE_NAME"   "$PHASE7_REPO_ROOT/deploy/helm/distributed-system"   --namespace "$PHASE7_NAMESPACE"   --values "$PHASE7_REPO_ROOT/deploy/helm/distributed-system/values-kind.yaml"   --set image.repository=distsys-node   --set image.tag=phase7-local   --wait --timeout 5m

kubectl -n "$PHASE7_NAMESPACE" rollout status   "statefulset/$PHASE7_RELEASE_NAME-distributed-system" --timeout=300s

trap - ERR INT TERM
echo "Phase 7 local cluster is ready."
