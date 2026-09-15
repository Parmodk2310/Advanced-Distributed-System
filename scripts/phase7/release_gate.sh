#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

readonly evidence_backup="$(mktemp -d)"
cleanup() {
  if [[ -d "$PHASE7_WORK_DIR/evidence" ]]; then
    cp "$PHASE7_WORK_DIR"/evidence/*.json "$evidence_backup"/ 2>/dev/null || true
  fi
  "$PHASE7_SCRIPT_DIR/cluster_down.sh"
  mkdir -p "$PHASE7_WORK_DIR/evidence"
  cp "$evidence_backup"/*.json "$PHASE7_WORK_DIR/evidence"/ 2>/dev/null || true
  rm -rf "$evidence_backup"
}
trap cleanup EXIT INT TERM

PYTHONPATH="$PHASE7_REPO_ROOT/src" python -m pytest "$PHASE7_REPO_ROOT/tests/deployment" -q
bash "$PHASE7_SCRIPT_DIR/cluster_up.sh"
PYTHONPATH="$PHASE7_REPO_ROOT/src" python "$PHASE7_SCRIPT_DIR/verify_cluster.py" \
  --output "$PHASE7_WORK_DIR/evidence/cluster.json"
PYTHONPATH="$PHASE7_REPO_ROOT/src" python "$PHASE7_SCRIPT_DIR/verify_persistence.py" \
  --output "$PHASE7_WORK_DIR/evidence/persistence.json"
bash "$PHASE7_SCRIPT_DIR/verify_rollback.sh"
printf '%s\n' '{"schema_version":1,"phase7_local_release_gate":"pass","aws_resources_created":false}' \
  > "$PHASE7_WORK_DIR/evidence/phase7-local-verification.json"
