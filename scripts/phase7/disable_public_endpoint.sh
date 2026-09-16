#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
command -v kubectl >/dev/null 2>&1 || exit 0
kubectl -n "$PHASE7_NAMESPACE" delete service "${PHASE7_RELEASE}-public" --ignore-not-found --wait=true
kubectl -n "$PHASE7_NAMESPACE" delete networkpolicy "${PHASE7_RELEASE}-temporary-public-ingress" --ignore-not-found --wait=true
if command -v aws >/dev/null 2>&1; then
  deadline=$((SECONDS+180))
  while (( SECONDS < deadline )); do
    lbs="$(aws resourcegroupstaggingapi get-resources --resource-type-filters elasticloadbalancing:loadbalancer --tag-filters Key=Phase,Values=7 Key=Environment,Values=phase7-demo --query 'ResourceTagMappingList[].ResourceARN' --output text 2>/dev/null || true)"
    [[ -z "${lbs//[[:space:]]/}" ]] && exit 0
    sleep 5
  done
  echo 'temporary Phase 7 load balancer still exists after 180s' >&2
  exit 1
fi
