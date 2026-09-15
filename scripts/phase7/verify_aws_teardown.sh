#!/usr/bin/env bash
set -euo pipefail
: "${AWS_REGION:=ap-south-1}"
: "${PHASE7_PROJECT_TAG:=advanced-distributed-system}"
command -v aws >/dev/null
fail=0
check_empty() {
  local label="$1" value="$2"
  if [[ -n "$value" && "$value" != "None" ]]; then
    printf 'remaining %s: %s\n' "$label" "$value" >&2
    fail=1
  fi
}
check_empty eks "$(aws eks list-clusters --region "$AWS_REGION" --query "clusters[?contains(@, 'phase7')]" --output text)"
check_empty nat "$(aws ec2 describe-nat-gateways --region "$AWS_REGION" --filter Name=state,Values=available,pending --query 'NatGateways[].NatGatewayId' --output text)"
check_empty load_balancers "$(aws elbv2 describe-load-balancers --region "$AWS_REGION" --query "LoadBalancers[?contains(LoadBalancerName, 'phase7')].LoadBalancerArn" --output text)"
check_empty volumes "$(aws ec2 describe-volumes --region "$AWS_REGION" --filters Name=status,Values=available Name=tag:Project,Values="$PHASE7_PROJECT_TAG" --query 'Volumes[].VolumeId' --output text)"
check_empty addresses "$(aws ec2 describe-addresses --region "$AWS_REGION" --filters Name=tag:Project,Values="$PHASE7_PROJECT_TAG" --query 'Addresses[].AllocationId' --output text)"
exit "$fail"
