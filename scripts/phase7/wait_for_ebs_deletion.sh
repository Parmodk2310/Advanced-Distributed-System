#!/usr/bin/env bash
set -euo pipefail

phase="${PHASE7_AWS_PHASE_TAG:-7}"
environment="${PHASE7_AWS_ENVIRONMENT:-phase7-demo}"
timeout_seconds="${PHASE7_EBS_WAIT_TIMEOUT_SECONDS:-600}"
poll_seconds="${PHASE7_EBS_WAIT_POLL_SECONDS:-10}"
region="${AWS_REGION:-ap-south-1}"

command -v aws >/dev/null
command -v jq >/dev/null

[[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || {
  echo "PHASE7_EBS_WAIT_TIMEOUT_SECONDS must be a positive integer" >&2
  exit 2
}
[[ "$poll_seconds" =~ ^[1-9][0-9]*$ ]] || {
  echo "PHASE7_EBS_WAIT_POLL_SECONDS must be a positive integer" >&2
  exit 2
}

deadline=$((SECONDS + timeout_seconds))
volumes='[]'

while (( SECONDS < deadline )); do
  volumes="$(
    aws ec2 describe-volumes \
      --region "$region" \
      --filters \
        "Name=tag:Phase,Values=$phase" \
        "Name=tag:Environment,Values=$environment" \
      --query 'Volumes[].{VolumeId:VolumeId,State:State,Attachments:Attachments}' \
      --output json
  )"

  if [[ "$(jq -r 'length' <<< "$volumes")" == "0" ]]; then
    jq -cn '{ebs_convergence:"pass",remaining_volumes:0}'
    exit 0
  fi

  printf 'waiting for Phase 7 EBS deletion; remaining volumes:
' >&2
  jq -r '.[] | "\(.VolumeId) state=\(.State)"' <<< "$volumes" >&2
  sleep "$poll_seconds"
done

printf 'timed out waiting for Phase 7 EBS volumes after %ss; remaining volumes:
' \
  "$timeout_seconds" >&2
jq . <<< "$volumes" >&2
exit 1
