#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${PHASE5_LOG_DIR:-$ROOT/.phase5-logs}"
DATA_DIR="${PHASE5_DATA_DIR:-$LOG_DIR/data}"
CERT_DIR="${PHASE5_CERT_DIR:-$ROOT/certs/generated}"
PID_FILE="$LOG_DIR/pids.env"
COMPOSE_FILE="$ROOT/docker/etcd/docker-compose.yml"
START_ETCD="${PHASE5_START_ETCD:-1}"
REMOVE_ETCD_VOLUME="${PHASE5_REMOVE_ETCD_VOLUME:-0}"
mkdir -p "$LOG_DIR" "$DATA_DIR"
: > "$PID_FILE"

for port in 18000 18001 18002; do
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    echo "port $port is already in use; refusing to start Phase-5 cluster" >&2
    exit 1
  fi
done

if [[ ! -f "$CERT_DIR/ca/ca.crt" ]]; then
  bash "$ROOT/scripts/generate_dev_certs.sh" "$CERT_DIR"
fi

cleanup() {
  trap - EXIT INT TERM
  if [[ -f "$PID_FILE" ]]; then
    while IFS='=' read -r _ pid; do
      if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null || true
      fi
    done < "$PID_FILE"
  fi
  sleep 0.2
  if [[ -f "$PID_FILE" ]]; then
    while IFS='=' read -r _ pid; do
      if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
        kill -KILL "$pid" 2>/dev/null || true
      fi
    done < "$PID_FILE"
  fi
  if [[ "$START_ETCD" == "1" ]] && command -v docker >/dev/null 2>&1; then
    if [[ "$REMOVE_ETCD_VOLUME" == "1" ]]; then
      docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
    else
      docker compose -f "$COMPOSE_FILE" down >/dev/null 2>&1 || true
    fi
  fi
}
trap cleanup EXIT INT TERM

if [[ "$START_ETCD" == "1" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required to launch Phase-5 etcd" >&2
    exit 1
  fi
  docker compose -f "$COMPOSE_FILE" up -d
  deadline=$((SECONDS + 30))
  until docker compose -f "$COMPOSE_FILE" exec -T etcd \
      etcdctl --endpoints=http://127.0.0.1:2379 endpoint health >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "etcd did not become healthy" >&2
      exit 1
    fi
    sleep 0.5
  done
fi

start_node() {
  local node_id="$1"
  local port="$2"
  local cert="$CERT_DIR/$node_id/node.crt"
  local key="$CERT_DIR/$node_id/node.key"

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
    CLUSTER_SEEDS= \
    CLUSTER_VIRTUAL_NODES=64 \
    CLUSTER_PROBE_INTERVAL_SECONDS=0.5 \
    CLUSTER_PING_TIMEOUT_SECONDS="${CLUSTER_PING_TIMEOUT_SECONDS:-0.75}" \
    CLUSTER_INDIRECT_TIMEOUT_SECONDS="${CLUSTER_INDIRECT_TIMEOUT_SECONDS:-1.50}" \
    CLUSTER_INDIRECT_PROBE_COUNT=2 \
    CLUSTER_SUSPICION_TIMEOUT_SECONDS="${CLUSTER_SUSPICION_TIMEOUT_SECONDS:-4.0}" \
    CLUSTER_DEAD_RETENTION_SECONDS=10 \
    CLUSTER_GOSSIP_INTERVAL_SECONDS=0.5 \
    CRDT_ENABLED=true \
    CRDT_REPLICATION_FACTOR=3 \
    CRDT_REPLICATION_QUEUE_CAPACITY=500 \
    CRDT_REPLICATION_WORKERS=1 \
    CRDT_REPLICATION_RETRY_MAX_ATTEMPTS=3 \
    CRDT_REPLICATION_RETRY_BASE_DELAY_SECONDS=0.05 \
    CRDT_REPLICATION_RETRY_MAX_DELAY_SECONDS=0.5 \
    CRDT_ANTI_ENTROPY_INTERVAL_SECONDS="${CRDT_ANTI_ENTROPY_INTERVAL_SECONDS:-1.0}" \
    CRDT_ANTI_ENTROPY_BATCH_SIZE=100 \
    PERSISTENCE_ENABLED=true \
    PERSISTENCE_DB_PATH="$DATA_DIR/$node_id.db" \
    PERSISTENCE_QUEUE_CAPACITY=100 \
    PERSISTENCE_BUSY_TIMEOUT_SECONDS=5 \
    PERSISTENCE_SQLITE_SYNCHRONOUS=NORMAL \
    ETCD_ENABLED=true \
    ETCD_ENDPOINTS="${ETCD_ENDPOINTS:-http://127.0.0.1:2379}" \
    ETCD_NAMESPACE="${ETCD_NAMESPACE:-/distsys/v1}" \
    ETCD_LEASE_TTL_SECONDS="${ETCD_LEASE_TTL_SECONDS:-6}" \
    ETCD_RENEW_INTERVAL_SECONDS="${ETCD_RENEW_INTERVAL_SECONDS:-2}" \
    TLS_ENABLED=true \
    MTLS_REQUIRED=true \
    TLS_CA_FILE="$CERT_DIR/ca/ca.crt" \
    TLS_CERT_FILE="$cert" \
    TLS_KEY_FILE="$key" \
    TLS_MIN_VERSION=TLSv1.3 \
    LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    python -m distsys.main >"$LOG_DIR/$node_id.log" 2>&1 &

  local pid=$!
  printf '%s=%s\n' "$node_id" "$pid" >> "$PID_FILE"
}

start_node node-0 18000
sleep 0.8
start_node node-1 18001
sleep 0.8
start_node node-2 18002

echo "Phase-5 cluster running"
echo "Logs: $LOG_DIR"
echo "Data: $DATA_DIR"
echo "PID file: $PID_FILE"
wait
