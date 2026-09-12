# Advanced Distributed System — Phase 1

Phase 1 builds the trustworthy single-node foundation for the later distributed cluster.

## What Phase 1 proves

- Async TCP server/client using `asyncio`
- Fixed 8-byte frame header: `MAGIC(2) + VERSION(1) + TYPE(1) + BODY_LEN(4)`
- Protobuf envelope and task messages
- Correlation IDs
- Maximum-frame protection
- Correct TCP fragmentation handling via `readexactly()` and incremental decoding tests
- Task router with `echo`
- Explicit protocol/application errors
- Structured logging
- Graceful node lifecycle

Not included yet: multiprocessing, backpressure, retry, circuit breaker, gossip, CRDTs, etcd, TLS, Prometheus, Docker cluster, or Kubernetes.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows/WSL: use the appropriate activation command
python -m pip install -e '.[dev]'
```

If you change `proto/messages.proto`, regenerate the Python module:

```bash
make proto
```

## Run

Terminal 1:

```bash
export NODE_ID=node-0
export NODE_HOST=127.0.0.1
export NODE_PORT=8000
python -m distsys.main
```

Terminal 2:

```bash
python - <<'PY'
import asyncio
from distsys.client import DistributedClient

async def main():
    client = DistributedClient(host='127.0.0.1', port=8000)
    print(await client.request('echo', {'message': 'hello'}))

asyncio.run(main())
PY
```

## Test

```bash
pytest -q
```

## Phase-1 smoke benchmark

Keep the node running, then:

```bash
python scripts/smoke_test.py --requests 10000
```

The goal is correctness first: zero corrupted responses and zero failures before Phase 2 introduces CPU workers and overload controls.
