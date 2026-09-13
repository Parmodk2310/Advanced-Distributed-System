PYTHON ?= python

.PHONY: install install-dev proto test lint format quality run smoke phase2-smoke phase3-cluster phase3-smoke

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
