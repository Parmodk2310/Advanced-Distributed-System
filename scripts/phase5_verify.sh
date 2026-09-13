#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d -t phase5-verify-XXXXXX)"
LOG_DIR="$TMP_ROOT/logs"
CERT_DIR="$TMP_ROOT/certs"
mkdir -p "$LOG_DIR"
RUNNER_PID=""

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "$RUNNER_PID" ]] && kill -0 "$RUNNER_PID" 2>/dev/null; then
    kill -TERM "$RUNNER_PID" 2>/dev/null || true
    wait "$RUNNER_PID" 2>/dev/null || true
  fi
  docker compose -f "$ROOT/docker/etcd/docker-compose.yml" down -v >/dev/null 2>&1 || true
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT INT TERM

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for phase5-secure-smoke" >&2
  exit 1
fi

bash "$ROOT/scripts/generate_dev_certs.sh" "$CERT_DIR"

PHASE5_LOG_DIR="$LOG_DIR" \
PHASE5_DATA_DIR="$LOG_DIR/data" \
PHASE5_CERT_DIR="$CERT_DIR" \
PHASE5_START_ETCD=1 \
PHASE5_REMOVE_ETCD_VOLUME=1 \
ETCD_LEASE_TTL_SECONDS=6 \
ETCD_RENEW_INTERVAL_SECONDS=2 \
bash "$ROOT/scripts/run_phase5_cluster.sh" >"$LOG_DIR/launcher.log" 2>&1 &
RUNNER_PID=$!

for _ in $(seq 1 80); do
  if ! kill -0 "$RUNNER_PID" 2>/dev/null; then
    cat "$LOG_DIR/launcher.log" >&2 || true
    exit 1
  fi
  if [[ -f "$LOG_DIR/pids.env" ]] && [[ $(wc -l < "$LOG_DIR/pids.env") -ge 3 ]]; then
    break
  fi
  sleep 0.25
done
sleep 1

PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
python "$ROOT/scripts/phase5_smoke.py" \
  --cert-dir "$CERT_DIR" \
  --data-dir "$LOG_DIR/data"

PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
ETCD_LEASE_TTL_SECONDS=6 \
ETCD_RENEW_INTERVAL_SECONDS=2 \
python "$ROOT/scripts/phase5_restart_smoke.py" \
  --log-dir "$LOG_DIR" \
  --cert-dir "$CERT_DIR"

PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
ETCD_LEASE_TTL_SECONDS=6 \
ETCD_RENEW_INTERVAL_SECONDS=2 \
python "$ROOT/scripts/phase5_etcd_smoke.py" \
  --cert-dir "$CERT_DIR" \
  --outage-wait 3

echo "PHASE5_SMOKE=PASS"
