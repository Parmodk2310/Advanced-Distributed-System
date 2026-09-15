#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE=(
  docker compose
  -p distsys-phase6
  -f deploy/monitoring/docker-compose.yml
)

RUNNER_PID=""
CURRENT_LOG_DIR=""

stop_cluster() {
  if [[ -n "$RUNNER_PID" ]] &&
     kill -0 "$RUNNER_PID" 2>/dev/null; then
    kill -TERM "$RUNNER_PID" 2>/dev/null || true
    wait "$RUNNER_PID" 2>/dev/null || true
  fi

  RUNNER_PID=""

  "${COMPOSE[@]}" down -v --remove-orphans \
    >/dev/null 2>&1 || true
}

cleanup() {
  trap - EXIT INT TERM
  stop_cluster
}

trap cleanup EXIT INT TERM

wait_for_ready() {
  local startup_attempts
  local all

  startup_attempts="${PHASE6_STARTUP_ATTEMPTS:-1200}"
  all=0

  for _ in $(seq 1 "$startup_attempts"); do
    all=1

    for port in 9100 9101 9102; do
      curl -fsS \
        "http://127.0.0.1:$port/health/ready" \
        >/dev/null 2>&1 || all=0
    done

    if [[ "$all" == "1" ]]; then
      return 0
    fi

    if ! kill -0 "$RUNNER_PID" 2>/dev/null; then
      echo \
        "Phase 6 cluster runner exited during startup" \
        >&2

      tail -n 200 \
        "$CURRENT_LOG_DIR/runner.log" >&2 || true

      return 1
    fi

    sleep 0.5
  done

  echo \
    "Phase 6 cluster readiness timed out after ${startup_attempts} attempts" \
    >&2

  for port in 9100 9101 9102; do
    curl -fsS \
      "http://127.0.0.1:$port/health/ready" \
      >/dev/null 2>&1 ||
      echo \
        "observability port $port is unavailable" \
        >&2
  done

  tail -n 200 \
    "$CURRENT_LOG_DIR/runner.log" >&2 || true

  return 1
}

start_cluster() {
  local routing="$1"

  stop_cluster

  CURRENT_LOG_DIR="$ROOT/.phase6-logs/$routing"

  rm -rf "$CURRENT_LOG_DIR"
  mkdir -p "$CURRENT_LOG_DIR"

  PHASE6_PEER_ROUTING="$routing" \
  PHASE6_LOG_DIR="$CURRENT_LOG_DIR" \
    bash scripts/run_phase6_cluster.sh \
    >"$CURRENT_LOG_DIR/runner.log" 2>&1 &

  RUNNER_PID=$!

  wait_for_ready

  echo \
    "Phase 6 ${routing} cluster ready"
}


# ------------------------------------------------------------
# Quality
# ------------------------------------------------------------

env \
  -u RUN_CHAOS_TESTS \
  -u RUN_PERFORMANCE_TESTS \
  -u PHASE6_PEER_PROXY_MAP \
  make quality


# ------------------------------------------------------------
# Healthy baseline
#
# Toxiproxy containers may exist in the monitoring stack, but
# node-to-node traffic bypasses them completely in direct mode.
# ------------------------------------------------------------

start_cluster direct

PYTHONPATH=src \
  python scripts/phase6_observability_smoke.py

PYTHONPATH=src \
  python scripts/phase6_monitoring_smoke.py \
    --cert-dir certs/generated

RUN_PERFORMANCE_TESTS=1 \
PYTHONPATH=src \
  python scripts/benchmark.py \
    --profile quick \
    --workload task

RUN_PERFORMANCE_TESTS=1 \
PYTHONPATH=src \
  python scripts/benchmark.py \
    --profile quick \
    --workload crdt


# ------------------------------------------------------------
# Chaos profile
#
# Start a fresh cluster whose node-to-node paths explicitly
# traverse the Toxiproxy endpoints.
# ------------------------------------------------------------

stop_cluster

start_cluster proxy

for scenario in \
  network-delay \
  partition \
  etcd-outage \
  node-kill
do
  RUN_CHAOS_TESTS=1 \
  PYTHONPATH=src \
    python scripts/chaos.py \
      "$scenario" \
      --target node-1 \
      --max-seconds 30 \
      --manifest "$CURRENT_LOG_DIR/manifest.json"

  sleep 1
done

echo "Phase 6 release gate passed"
