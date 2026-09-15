#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
NODE_ID="${1:?node id required}"
NODE_PORT="${2:?node port required}"
OBS_PORT="${3:?observability port required}"
LOG_DIR="${PHASE6_LOG_DIR:-$ROOT/.phase6-logs}"
DATA_DIR="$LOG_DIR/data"
CERT_DIR="${PHASE6_CERT_DIR:-$ROOT/certs/generated}"
MANIFEST="$LOG_DIR/manifest.json"
mkdir -p "$LOG_DIR" "$DATA_DIR"

case "$NODE_ID:$NODE_PORT:$OBS_PORT" in
  node-0:18000:9100|node-1:18001:9101|node-2:18002:9102) ;;
  *) echo "refusing unmanaged Phase 6 node tuple" >&2; exit 2 ;;
esac

if [[ ! -f "$CERT_DIR/$NODE_ID/node.crt" ]]; then
  echo "missing certificate for $NODE_ID; run make phase5-certs first" >&2
  exit 2
fi

# Idempotent restart: if manifest says this node is already alive, do nothing.
if [[ -f "$MANIFEST" ]]; then
  old_pid="$(python - "$MANIFEST" "$NODE_ID" <<'PY'
import json,sys
try: print(json.load(open(sys.argv[1]))['pids'][sys.argv[2]]['pid'])
except Exception: print('')
PY
)"
  if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
    state="$(awk '{print $3}' "/proc/$old_pid/stat" 2>/dev/null || true)"
    if [[ "$state" != "Z" ]]; then
      echo "$NODE_ID already running as PID $old_pid"
      exit 0
    fi
  fi
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export NODE_ID NODE_PORT OBSERVABILITY_PORT="$OBS_PORT"
export NODE_HOST=127.0.0.1 CPU_WORKERS=1 CPU_QUEUE_CAPACITY=100 RATE_LIMIT_RPS=500 RATE_LIMIT_BURST=100 REQUEST_TIMEOUT_SECONDS=5
export CLUSTER_ENABLED=true CLUSTER_SEEDS= CLUSTER_VIRTUAL_NODES=64 CLUSTER_PROBE_INTERVAL_SECONDS=0.5 CLUSTER_PING_TIMEOUT_SECONDS=0.75 CLUSTER_INDIRECT_TIMEOUT_SECONDS=1.5 CLUSTER_INDIRECT_PROBE_COUNT=2 CLUSTER_SUSPICION_TIMEOUT_SECONDS=4 CLUSTER_DEAD_RETENTION_SECONDS=10 CLUSTER_GOSSIP_INTERVAL_SECONDS=0.5
export CRDT_ENABLED=true CRDT_REPLICATION_FACTOR=3 CRDT_REPLICATION_QUEUE_CAPACITY=500 CRDT_REPLICATION_WORKERS=1 CRDT_REPLICATION_RETRY_MAX_ATTEMPTS=3 CRDT_REPLICATION_RETRY_BASE_DELAY_SECONDS=0.05 CRDT_REPLICATION_RETRY_MAX_DELAY_SECONDS=0.5 CRDT_ANTI_ENTROPY_INTERVAL_SECONDS=1.0 CRDT_ANTI_ENTROPY_BATCH_SIZE=100
export PERSISTENCE_ENABLED=true PERSISTENCE_DB_PATH="$DATA_DIR/$NODE_ID.db" PERSISTENCE_QUEUE_CAPACITY=100 PERSISTENCE_BUSY_TIMEOUT_SECONDS=5 PERSISTENCE_SQLITE_SYNCHRONOUS=NORMAL
export ETCD_ENABLED=true ETCD_ENDPOINTS=http://127.0.0.1:12379 ETCD_NAMESPACE=/distsys/v1 ETCD_LEASE_TTL_SECONDS=6 ETCD_RENEW_INTERVAL_SECONDS=2
export TLS_ENABLED=true MTLS_REQUIRED=true TLS_CA_FILE="$CERT_DIR/ca/ca.crt" TLS_CERT_FILE="$CERT_DIR/$NODE_ID/node.crt" TLS_KEY_FILE="$CERT_DIR/$NODE_ID/node.key" TLS_MIN_VERSION=TLSv1.3
export OBSERVABILITY_ENABLED=true OBSERVABILITY_HOST="${PHASE6_OBSERVABILITY_HOST:-0.0.0.0}" METRICS_ENABLED=true TRACING_ENABLED=true OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 OTEL_SERVICE_NAME=distsys-node OTEL_TRACE_SAMPLE_RATIO=0.10 OTEL_EXPORT_TIMEOUT_SECONDS=2.0
PHASE6_PEER_ROUTING="${PHASE6_PEER_ROUTING:-direct}"

case "$PHASE6_PEER_ROUTING" in
  direct)
    unset RUN_CHAOS_TESTS PHASE6_PEER_PROXY_MAP
    ;;
  proxy)
    export RUN_CHAOS_TESTS=1
    export PHASE6_PEER_PROXY_MAP='node-0=127.0.0.1:19100,node-1=127.0.0.1:19101,node-2=127.0.0.1:19102'
    ;;
  *)
    echo "unsupported PHASE6_PEER_ROUTING: $PHASE6_PEER_ROUTING" >&2
    exit 2
    ;;
esac
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

nohup python -m distsys.main >>"$LOG_DIR/$NODE_ID.log" 2>&1 &
pid=$!
sleep 0.15
kill -0 "$pid"
start_token="$(awk '{print $22}' "/proc/$pid/stat")"
python - "$MANIFEST" "$LOG_DIR" "$NODE_ID" "$pid" "$start_token" "$NODE_PORT" "$OBS_PORT" <<'PY'
import json,sys
from pathlib import Path
path=Path(sys.argv[1]); runtime=Path(sys.argv[2]).resolve(); node=sys.argv[3]; pid=int(sys.argv[4]); token=sys.argv[5]; port=sys.argv[6]; obs=sys.argv[7]
try: data=json.loads(path.read_text())
except Exception: data={}
data.update({'runtime_dir':str(runtime),'proxies':['peer-node-0','peer-node-1','peer-node-2','etcd'],'services':['etcd']})
data.setdefault('pids',{})[node]={'pid':pid,'start_token':token,'cmdline_contains':'distsys.main','restart_argv':['bash','scripts/phase6_start_node.sh',node,port,obs]}
tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,indent=2,sort_keys=True)); tmp.replace(path)
PY
echo "started $NODE_ID pid=$pid app=$NODE_PORT obs=$OBS_PORT"
