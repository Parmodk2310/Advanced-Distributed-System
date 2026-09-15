#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
kubectl -n "$PHASE7_NAMESPACE" patch service "$PHASE7_RELEASE-distributed-system" \
  --type merge --patch '{"spec":{"type":"ClusterIP"}}'
kubectl -n "$PHASE7_NAMESPACE" wait --for=delete pod \
  --selector service.k8s.aws/stack="$PHASE7_RELEASE-distributed-system" --timeout=2m 2>/dev/null || true
