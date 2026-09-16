#!/usr/bin/env bash
set -euo pipefail
phase="${PHASE7_AWS_PHASE_TAG:-7}"
environment="${PHASE7_AWS_ENVIRONMENT:-phase7-demo}"
command -v aws >/dev/null
deadline=$((SECONDS+180))
while (( SECONDS < deadline )); do
  remaining="$(aws resourcegroupstaggingapi get-resources \
    --tag-filters "Key=Phase,Values=$phase" "Key=Environment,Values=$environment" \
    --query 'ResourceTagMappingList[].ResourceARN' --output text)"
  if [[ -z "${remaining//[[:space:]]/}" ]]; then
    printf '%s\n' '{"aws_teardown":"pass","unexpected_tagged_resources":0}'
    exit 0
  fi
  sleep 10
done
printf 'unexpected tagged Phase 7 resources remain after 180s:\n%s\n' "$remaining" >&2
exit 1
