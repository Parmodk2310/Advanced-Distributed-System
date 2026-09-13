#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${PHASE3_LOG_DIR:-$ROOT/.phase3-logs}"
PID_FILE="$LOG_DIR/pids.env"
mkdir -p "$LOG_DIR"
: > "$PID_FILE"

for port in 18000 18001 18002; do
  if ss -ltn "sport = :$port" | grep -q LISTEN; then
    echo "port $port is already in use; refusing to start cluster" >&2
    exit 1
  fi
done

pids=()
cleanup() {
  trap - EXIT INT TERM
  for pid in "${pids[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

start_node() {
  local node_id="$1"
  local port="$2"
  local seeds="$3"

  env \
    PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
    NODE_ID="$node_id" \
    NODE_HOST=127.0.0.1 \
    NODE_PORT="$port" \
    CPU_WORKERS=1 \
    CPU_QUEUE_CAPACITY=100 \
    RATE_LIMIT_RPS=500 \
    RATE_LIMIT_BURST=100 \
    REQUEST_TIMEOUT_SECONDS=5 \
    CLUSTER_ENABLED=true \
    CLUSTER_SEEDS="$seeds" \
    CLUSTER_VIRTUAL_NODES=64 \
    CLUSTER_PROBE_INTERVAL_SECONDS=1.0 \
    CLUSTER_PING_TIMEOUT_SECONDS=0.25 \
    CLUSTER_INDIRECT_TIMEOUT_SECONDS=0.50 \
    CLUSTER_INDIRECT_PROBE_COUNT=2 \
    CLUSTER_SUSPICION_TIMEOUT_SECONDS=3.0 \
    CLUSTER_DEAD_RETENTION_SECONDS=30.0 \
    CLUSTER_GOSSIP_INTERVAL_SECONDS=1.0 \
    LOG_LEVEL=INFO \
    python -m distsys.main >"$LOG_DIR/$node_id.log" 2>&1 &

  local pid=$!
  pids+=("$pid")
  printf '%s=%s\n' "$node_id" "$pid" >> "$PID_FILE"
}

start_node node-0 18000 ""
sleep 0.3
start_node node-1 18001 "127.0.0.1:18000"
start_node node-2 18002 "127.0.0.1:18000"

echo "Phase-3 cluster running. Logs: $LOG_DIR"
echo "PID file: $PID_FILE"
echo "PIDs: ${pids[*]}"
wait
