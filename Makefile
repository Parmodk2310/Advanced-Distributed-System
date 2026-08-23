.PHONY: install certs proto test run docker-up docker-down clean

# Install dependencies
install:
	pip install -r requirements.txt

# Generate TLS certificates
certs:
	bash certs/generate.sh

# Compile protobuf (requires protoc)
proto:
	mkdir -p src/generated
	protoc -I=proto --python_out=src/generated proto/messages.proto

# Run tests
test:
	pytest tests/ -v --asyncio-mode=auto

# Run single node locally
run:
	PYTHONPATH=. python src/main.py

# Run 3-node cluster locally
cluster:
	bash scripts/run-cluster.sh

# Docker operations
docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down -v

docker-logs:
	docker-compose logs -f

# Code quality
format:
	black src/ tests/

lint:
	mypy src/ --ignore-missing-imports

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache