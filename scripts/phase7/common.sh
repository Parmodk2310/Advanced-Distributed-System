#!/usr/bin/env bash
set -euo pipefail
readonly PHASE7_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PHASE7_REPO_ROOT="$(cd "$PHASE7_SCRIPT_DIR/../.." && pwd -P)"
readonly PHASE7_WORK_DIR="$PHASE7_REPO_ROOT/.phase7"
readonly PHASE7_NAMESPACE="${PHASE7_NAMESPACE:-distsys}"
readonly PHASE7_RELEASE="${PHASE7_RELEASE:-phase7}"
readonly PHASE7_ETCD_RELEASE="${PHASE7_ETCD_RELEASE:-phase7-etcd}"
readonly PHASE7_KIND_CLUSTER="${PHASE7_KIND_CLUSTER:-distsys-phase7}"
readonly PHASE7_K3D_CLUSTER="${PHASE7_K3D_CLUSTER:-distsys-phase7-k3d}"
readonly PHASE7_IMAGE="${PHASE7_IMAGE:-distsys-node:phase7-local}"
readonly PHASE7_HELM_TIMEOUT="${PHASE7_HELM_TIMEOUT:-5m}"
phase7_require_command(){ command -v "$1" >/dev/null 2>&1 || { printf 'required command is unavailable: %s
' "$1" >&2; return 1; }; }
phase7_validate_work_dir(){
  case "$PHASE7_WORK_DIR" in "$PHASE7_REPO_ROOT/.phase7") ;; *) printf 'refusing unsafe Phase 7 work directory: %s
' "$PHASE7_WORK_DIR" >&2; return 1;; esac
  test -n "$PHASE7_REPO_ROOT" && test "$PHASE7_REPO_ROOT" != "/"
}
phase7_prepare_work_dir(){ phase7_validate_work_dir; mkdir -p "$PHASE7_WORK_DIR/evidence"; chmod 700 "$PHASE7_WORK_DIR"; }
phase7_chart_dir(){ printf '%s
' "$PHASE7_REPO_ROOT/deploy/helm/distributed-system"; }
phase7_etcd_chart_dir(){ printf '%s
' "$PHASE7_REPO_ROOT/deploy/helm/etcd"; }
