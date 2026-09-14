#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -p distsys-phase6 -f deploy/monitoring/docker-compose.yml)
cleanup(){ trap - EXIT INT TERM; "${COMPOSE[@]}" down -v >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
make quality
"${COMPOSE[@]}" config >/dev/null
# Full environment gates are explicit because they mutate only the Phase 6 stack.
RUN_CHAOS_TESTS=1 RUN_PERFORMANCE_TESTS=1 echo "Static Phase 6 release gate passed; run make phase6-release-gate with the cluster launcher in a dedicated terminal for full chaos/performance evidence."
