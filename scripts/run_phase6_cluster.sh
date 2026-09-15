#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE=(
  docker compose
  -p distsys-phase6
  -f deploy/monitoring/docker-compose.yml
)

LOG_DIR="${PHASE6_LOG_DIR:-$ROOT/.phase6-logs}"
RUNNER_IDLE_PID=""

mkdir -p "$LOG_DIR"

PHASE6_PEER_ROUTING="${PHASE6_PEER_ROUTING:-direct}"

case "$PHASE6_PEER_ROUTING" in
  direct)
    unset RUN_CHAOS_TESTS
    unset PHASE6_PEER_PROXY_MAP
    ;;

  proxy)
    export RUN_CHAOS_TESTS=1
    export PHASE6_PEER_PROXY_MAP="node-0=toxiproxy:19100,node-1=toxiproxy:19101,node-2=toxiproxy:19102"
    ;;

  *)
    echo "unsupported PHASE6_PEER_ROUTING: $PHASE6_PEER_ROUTING" >&2
    exit 2
    ;;
esac

cleanup() {
  trap - EXIT

  if [[ -n "$RUNNER_IDLE_PID" ]] &&
     kill -0 "$RUNNER_IDLE_PID" 2>/dev/null
  then
    kill -TERM "$RUNNER_IDLE_PID" 2>/dev/null || true
    wait "$RUNNER_IDLE_PID" 2>/dev/null || true
    RUNNER_IDLE_PID=""
  fi

  "${COMPOSE[@]}" \
    down -v --remove-orphans \
    >/dev/null 2>&1 || true
}

terminate() {
  trap - INT TERM
  cleanup
  exit 0
}

trap cleanup EXIT
trap terminate INT TERM

for port in \
  18000 18001 18002 \
  9100 9101 9102 \
  12379 \
  19100 19101 19102 \
  3000 3200 4318 8474 9090
do
  if ss -ltn "sport = :$port" 2>/dev/null |
     grep -q LISTEN
  then
    echo \
      "port $port already in use; refusing Phase 6 startup" \
      >&2
    exit 1
  fi
done

if [[ ! -f certs/generated/ca/ca.crt ]]; then
  bash scripts/generate_dev_certs.sh certs/generated
fi

echo "Phase 6: building node image"

"${COMPOSE[@]}" build node-0 node-1 node-2

echo "Phase 6: starting infrastructure"

"${COMPOSE[@]}" up -d etcd toxiproxy tempo otel-collector

TOXIPROXY_READY=0

for _ in $(seq 1 60); do
  if curl -fsS \
    http://127.0.0.1:8474/proxies \
    >/dev/null 2>&1
  then
    TOXIPROXY_READY=1
    break
  fi

  sleep 0.5
done

if [[ "$TOXIPROXY_READY" != "1" ]]; then
  echo "Toxiproxy API did not become ready" >&2
  "${COMPOSE[@]}" ps -a >&2 || true
  exit 1
fi

echo "Phase 6: bootstrapping managed proxies"

PYTHONPATH=src \
python scripts/phase6_proxy_bootstrap.py

echo "Phase 6: starting distributed nodes"

"${COMPOSE[@]}" up -d node-0 node-1 node-2

NODES_READY=0

for _ in $(seq 1 120); do
  NODES_READY=1

  for port in 9100 9101 9102; do
    if ! curl -fsS \
      "http://127.0.0.1:${port}/health/ready" \
      >/dev/null 2>&1
    then
      NODES_READY=0
    fi
  done

  if [[ "$NODES_READY" == "1" ]]; then
    break
  fi

  sleep 0.5
done

if [[ "$NODES_READY" != "1" ]]; then
  echo "Phase 6 nodes did not become ready" >&2

  "${COMPOSE[@]}" ps -a >&2 || true

  "${COMPOSE[@]}" logs \
    --tail=120 \
    node-0 node-1 node-2 \
    >&2 || true

  exit 1
fi

echo "Phase 6: starting monitoring services"

"${COMPOSE[@]}" up -d prometheus grafana

python - "$LOG_DIR/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
runtime = path.parent.resolve()

data = {
    "runtime_dir": str(runtime),
    "pids": {},
    "proxies": [
        "peer-node-0",
        "peer-node-1",
        "peer-node-2",
        "etcd",
    ],
    "services": [
        "etcd",
        "node-0",
        "node-1",
        "node-2",
    ],
}

tmp = path.with_suffix(".tmp")
tmp.write_text(
    json.dumps(
        data,
        indent=2,
        sort_keys=True,
    ),
    encoding="utf-8",
)

tmp.replace(path)
PY

echo \
  "Phase 6 Docker cluster running; manifest: $LOG_DIR/manifest.json"

while true; do
  sleep 3600 &
  RUNNER_IDLE_PID=$!
  wait "$RUNNER_IDLE_PID"
  RUNNER_IDLE_PID=""
done
