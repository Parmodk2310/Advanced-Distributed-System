PYTHON ?= python

.PHONY: install install-dev proto test lint format quality run smoke phase2-smoke \
	phase3-cluster phase3-smoke phase4-cluster phase4-smoke \
	phase5-certs phase5-etcd-up phase5-etcd-down phase5-etcd-integration \
	phase5-cluster phase5-smoke phase5-restart-smoke phase5-etcd-smoke phase5-secure-smoke

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e '.[dev]'

proto:
	$(PYTHON) -m grpc_tools.protoc \
		-I proto \
		--python_out=src/distsys/proto \
		--pyi_out=src/distsys/proto \
		proto/messages.proto

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check src tests scripts

format:
	$(PYTHON) -m black src tests scripts

quality:
	$(PYTHON) -m pytest -q
	$(PYTHON) -m ruff check src tests scripts
	$(PYTHON) -m black --check src tests scripts
	$(PYTHON) -m mypy src/distsys

run:
	$(PYTHON) -m distsys.main

smoke:
	$(PYTHON) scripts/smoke_test.py --requests 10000

phase2-smoke:
	$(PYTHON) scripts/phase2_smoke.py

phase3-cluster:
	bash scripts/run_phase3_cluster.sh

phase3-smoke:
	$(PYTHON) scripts/phase3_smoke.py --host 127.0.0.1 --ports 18000 18001 18002

phase4-cluster:
	bash scripts/run_phase4_cluster.sh

phase4-smoke:
	$(PYTHON) scripts/phase4_smoke.py --host 127.0.0.1 --ports 18000 18001 18002

phase5-certs:
	bash scripts/generate_dev_certs.sh certs/generated

phase5-etcd-up:
	docker compose -f docker/etcd/docker-compose.yml up -d

phase5-etcd-down:
	docker compose -f docker/etcd/docker-compose.yml down -v

phase5-etcd-integration:
	bash -c 'set -euo pipefail; \
		trap "docker compose -f docker/etcd/docker-compose.yml down -v >/dev/null 2>&1 || true" EXIT; \
		docker compose -f docker/etcd/docker-compose.yml up -d; \
		for i in $$(seq 1 60); do \
			docker compose -f docker/etcd/docker-compose.yml exec -T etcd etcdctl --endpoints=http://127.0.0.1:2379 endpoint health >/dev/null 2>&1 && break; \
			sleep 0.5; \
		done; \
		RUN_ETCD_INTEGRATION=1 PYTHONPATH=src $(PYTHON) -m pytest -q \
			tests/integration/test_etcd_registration.py \
			tests/integration/test_etcd_lease_expiry.py \
			tests/integration/test_etcd_outage.py'

phase5-cluster:
	bash scripts/run_phase5_cluster.sh

phase5-smoke:
	PYTHONPATH=src $(PYTHON) scripts/phase5_smoke.py \
		--cert-dir certs/generated \
		--data-dir .phase5-logs/data

phase5-restart-smoke:
	PYTHONPATH=src $(PYTHON) scripts/phase5_restart_smoke.py \
		--log-dir .phase5-logs \
		--cert-dir certs/generated

phase5-etcd-smoke:
	PYTHONPATH=src $(PYTHON) scripts/phase5_etcd_smoke.py --cert-dir certs/generated

phase5-secure-smoke:
	bash scripts/phase5_verify.sh

.PHONY: phase6-monitoring-up phase6-monitoring-down phase6-cluster \
	phase6-observability-smoke phase6-chaos phase6-benchmark phase6-release-gate

.PHONY: phase7-image phase7-image-inspect

PHASE7_IMAGE ?= distsys-node:phase7-local

phase7-image:
	docker build --pull --tag $(PHASE7_IMAGE) .

phase7-image-inspect:
	docker inspect $(PHASE7_IMAGE) --format '{{.Config.User}} {{json .Config.Entrypoint}}'
	docker run --rm --entrypoint python $(PHASE7_IMAGE) -c 'import distsys; print("import-ok")'

phase6-monitoring-up:
	docker compose -p distsys-phase6 -f deploy/monitoring/docker-compose.yml up -d

phase6-monitoring-down:
	docker compose -p distsys-phase6 -f deploy/monitoring/docker-compose.yml down -v

phase6-cluster:
	bash scripts/run_phase6_cluster.sh

phase6-observability-smoke:
	PYTHONPATH=src $(PYTHON) scripts/phase6_observability_smoke.py
	PYTHONPATH=src $(PYTHON) scripts/phase6_monitoring_smoke.py --cert-dir certs/generated

phase6-chaos:
	RUN_CHAOS_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/chaos.py network-delay --target node-1
	RUN_CHAOS_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/chaos.py partition --target node-1
	RUN_CHAOS_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/chaos.py etcd-outage --target node-1
	RUN_CHAOS_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/chaos.py node-kill --target node-1

phase6-benchmark:
	RUN_PERFORMANCE_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/benchmark.py --profile quick --workload task
	RUN_PERFORMANCE_TESTS=1 PYTHONPATH=src $(PYTHON) scripts/benchmark.py --profile quick --workload crdt

phase6-release-gate:
	bash scripts/phase6_release_gate.sh
