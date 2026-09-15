#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RUNNER_PID=""
cleanup(){
  trap - EXIT INT TERM
  if [[ -n "$RUNNER_PID" ]] && kill -0 "$RUNNER_PID" 2>/dev/null; then
    kill -TERM "$RUNNER_PID" 2>/dev/null || true
    wait "$RUNNER_PID" 2>/dev/null || true
  fi
  docker compose -p distsys-phase6 -f deploy/monitoring/docker-compose.yml down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

env -u RUN_CHAOS_TESTS -u PHASE6_PEER_PROXY_MAP make quality
mkdir -p .phase6-logs
bash scripts/run_phase6_cluster.sh >.phase6-logs/runner.log 2>&1 &
RUNNER_PID=$!
STARTUP_ATTEMPTS="${PHASE6_STARTUP_ATTEMPTS:-1200}"
all=0
for _ in $(seq 1 "$STARTUP_ATTEMPTS"); do
  all=1
  for port in 9100 9101 9102; do
    curl -fsS "http://127.0.0.1:$port/health/ready" >/dev/null 2>&1 || all=0
  done
  [[ "$all" == 1 ]] && break
  if ! kill -0 "$RUNNER_PID" 2>/dev/null; then
    echo "Phase 6 cluster runner exited during startup" >&2
    tail -n 200 .phase6-logs/runner.log >&2
    exit 1
  fi
  sleep .5
done
if [[ "$all" != 1 ]]; then
  echo "Phase 6 cluster readiness timed out after $STARTUP_ATTEMPTS attempts" >&2
  for port in 9100 9101 9102; do
    curl -fsS "http://127.0.0.1:$port/health/ready" >/dev/null 2>&1 ||
      echo "observability port $port is unavailable" >&2
  done
  tail -n 200 .phase6-logs/runner.log >&2
  exit 1
fi

PYTHONPATH=src python scripts/phase6_observability_smoke.py
PYTHONPATH=src python scripts/phase6_monitoring_smoke.py --cert-dir certs/generated

# Benchmark the clean baseline before chaos mutates circuit-breaker and membership
# state. Chaos assertions run afterward and retain their own recovery checks.
RUN_PERFORMANCE_TESTS=1 PYTHONPATH=src python scripts/benchmark.py --profile quick --workload task
RUN_PERFORMANCE_TESTS=1 PYTHONPATH=src python scripts/benchmark.py --profile quick --workload crdt

for scenario in network-delay partition etcd-outage node-kill; do
  RUN_CHAOS_TESTS=1 PYTHONPATH=src python scripts/chaos.py "$scenario" --target node-1 --max-seconds 30
  sleep 1
done

echo "Phase 6 release gate passed"
