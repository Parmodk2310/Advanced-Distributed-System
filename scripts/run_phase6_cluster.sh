#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -p distsys-phase6 -f deploy/monitoring/docker-compose.yml)
LOG_DIR="${PHASE6_LOG_DIR:-$ROOT/.phase6-logs}"
mkdir -p "$LOG_DIR"

cleanup() {
  trap - EXIT
  if [[ -f "$LOG_DIR/manifest.json" ]]; then
    python - "$LOG_DIR/manifest.json" <<'PY'
import json,os,signal,sys,time
try: data=json.load(open(sys.argv[1]))
except Exception: data={}
for item in data.get('pids',{}).values():
    pid=int(item.get('pid',0))
    try: os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError,PermissionError): pass
time.sleep(.3)
for item in data.get('pids',{}).values():
    pid=int(item.get('pid',0))
    try: os.kill(pid, 0); os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError,PermissionError): pass
PY
  fi
  "${COMPOSE[@]}" down -v >/dev/null 2>&1 || true
}

terminate() {
  trap - INT TERM
  cleanup
  exit 0
}

trap cleanup EXIT
trap terminate INT TERM

for port in 18000 18001 18002 9100 9101 9102 12379 19100 19101 19102 3000 3200 4318 8474 9090; do
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    echo "port $port already in use; refusing Phase 6 startup" >&2; exit 1
  fi
done
[[ -f certs/generated/ca/ca.crt ]] || bash scripts/generate_dev_certs.sh certs/generated
"${COMPOSE[@]}" up -d
for _ in $(seq 1 60); do
  curl -fsS http://127.0.0.1:8474/proxies >/dev/null 2>&1 && break
  sleep .5
done
PYTHONPATH=src python scripts/phase6_proxy_bootstrap.py
bash scripts/phase6_start_node.sh node-0 18000 9100
sleep .8
bash scripts/phase6_start_node.sh node-1 18001 9101
sleep .8
bash scripts/phase6_start_node.sh node-2 18002 9102

echo "Phase 6 cluster running; manifest: $LOG_DIR/manifest.json"
while true; do sleep 3600; done
