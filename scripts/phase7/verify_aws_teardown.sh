#!/usr/bin/env bash
set -euo pipefail

phase="${PHASE7_AWS_PHASE_TAG:-7}"
environment="${PHASE7_AWS_ENVIRONMENT:-phase7-demo}"
timeout_seconds="${PHASE7_TEARDOWN_TIMEOUT_SECONDS:-600}"
poll_seconds="${PHASE7_TEARDOWN_POLL_SECONDS:-10}"
region="${AWS_REGION:-ap-south-1}"

: "${PHASE7_TF_STATE_BUCKET:?PHASE7_TF_STATE_BUCKET is required}"
: "${PHASE7_TF_LOCK_TABLE:?PHASE7_TF_LOCK_TABLE is required}"

command -v aws >/dev/null
command -v jq >/dev/null

[[ "$timeout_seconds" =~ ^[1-9][0-9]*$ ]] || {
  echo "PHASE7_TEARDOWN_TIMEOUT_SECONDS must be a positive integer" >&2
  exit 2
}

[[ "$poll_seconds" =~ ^[1-9][0-9]*$ ]] || {
  echo "PHASE7_TEARDOWN_POLL_SECONDS must be a positive integer" >&2
  exit 2
}

account_id="$(
  aws sts get-caller-identity \
    --query Account \
    --output text
)"

state_bucket="$PHASE7_TF_STATE_BUCKET"
lock_table="$PHASE7_TF_LOCK_TABLE"
state_bucket_arn="arn:aws:s3:::${state_bucket}"
lock_table_arn="arn:aws:dynamodb:${region}:${account_id}:table/${lock_table}"
volume_arn_prefix="arn:aws:ec2:${region}:${account_id}:volume/"

describe_error="$(mktemp)"
trap 'rm -f "$describe_error"' EXIT

deadline=$((SECONDS + timeout_seconds))
unexpected='[]'

while (( SECONDS < deadline )); do
  tagged_resources="$(
    aws resourcegroupstaggingapi get-resources \
      --region "$region" \
      --tag-filters \
        "Key=Phase,Values=$phase" \
        "Key=Environment,Values=$environment" \
      --query 'ResourceTagMappingList[].ResourceARN' \
      --output json
  )"

  unexpected="$(
    jq -ce \
      --arg state_bucket "$state_bucket_arn" \
      --arg lock_table "$lock_table_arn" \
      '[
        .[]
        | select(. != $state_bucket and . != $lock_table)
      ]' <<< "$tagged_resources"
  )"

  verified_unexpected='[]'
  stale_tagging_records=0

  while IFS= read -r arn; do
    if [[ "$arn" == "${volume_arn_prefix}"* ]]; then
      volume_id="${arn##*/}"
      : > "$describe_error"

      if aws ec2 describe-volumes \
        --region "$region" \
        --volume-ids "$volume_id" \
        --query 'Volumes[].VolumeId' \
        --output json \
        >/dev/null 2>"$describe_error"
      then
        :
      elif grep -q 'InvalidVolume.NotFound' "$describe_error"; then
        stale_tagging_records=$((stale_tagging_records + 1))
        continue
      else
        printf 'failed to verify EBS volume %s:\n' "$volume_id" >&2
        cat "$describe_error" >&2
        exit 1
      fi
    fi

    verified_unexpected="$(
      jq -cn \
        --argjson resources "$verified_unexpected" \
        --arg arn "$arn" \
        '$resources + [$arn]'
    )"
  done < <(jq -r '.[]' <<< "$unexpected")

  unexpected="$verified_unexpected"

  if [[ "$(jq -r 'length' <<< "$unexpected")" == "0" ]]; then
    jq -cn \
      --arg state_bucket "$state_bucket_arn" \
      --arg lock_table "$lock_table_arn" \
      --argjson stale_tagging_records "$stale_tagging_records" \
      '{
        aws_teardown: "pass",
        unexpected_tagged_resources: 0,
        stale_tagging_records_ignored: $stale_tagging_records,
        retained_backend_resources: [
          $state_bucket,
          $lock_table
        ]
      }'
    exit 0
  fi

  sleep "$poll_seconds"
done

printf 'unexpected tagged Phase 7 resources remain after %ss:\n' \
  "$timeout_seconds" >&2
jq -r '.[]' <<< "$unexpected" >&2
exit 1
