#!/usr/bin/env bash
set -euo pipefail

PHASE7_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PHASE7_REPO_ROOT="$(cd "$PHASE7_SCRIPT_DIR/../.." && pwd -P)"
PHASE7_CLUSTER_NAME="distsys-phase7"
PHASE7_NAMESPACE="distsys"
PHASE7_RELEASE_NAME="phase7"
PHASE7_IMAGE="distsys-node:phase7-local"
PHASE7_WORK_DIR="$PHASE7_REPO_ROOT/.phase7"
PHASE7_TLS_DIR="$PHASE7_WORK_DIR/tls"

case "$PHASE7_WORK_DIR" in
  "$PHASE7_REPO_ROOT/.phase7") ;;
  *)
    echo "refusing unsafe Phase 7 workspace: $PHASE7_WORK_DIR" >&2
    exit 2
    ;;
esac

require_tool() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "required tool not found: $1" >&2
    exit 2
  }
}

safe_remove_dir() {
  local target="$1"
  case "$target" in
    "$PHASE7_WORK_DIR"|"$PHASE7_WORK_DIR"/*)
      rm -rf -- "$target"
      ;;
    *)
      echo "refusing unsafe Phase 7 removal: $target" >&2
      return 2
      ;;
  esac
}
