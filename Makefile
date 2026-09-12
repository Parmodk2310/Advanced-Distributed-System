PYTHON ?= python

.PHONY: install install-dev proto test lint format run smoke

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e '.[dev]'

.PHONY: proto

proto:
	python -m grpc_tools.protoc \
		-I proto \
		--python_out=src/distsys/proto \
		--pyi_out=src/distsys/proto \
		proto/messages.proto
test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check src tests

format:
	$(PYTHON) -m black src tests scripts

run:
	$(PYTHON) -m distsys.main

smoke:
	$(PYTHON) scripts/smoke_test.py --requests 10000


.PHONY: quality

quality:
	python -m pytest -q
	ruff check src tests scripts
	black --check src tests scripts
	mypy src/distsys