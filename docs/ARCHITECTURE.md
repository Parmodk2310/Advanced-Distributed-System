
# System Architecture Deep Dive

## 1. Design Principles

### 1.1 Separation of Concerns

The system is organized into 7 independent layers, each with a single responsibility:

| Layer | Responsibility | Key Files |
|-------|---------------|-----------|
| **Protocol** | Serialization, encryption, framing | `protocol/message.py`, `protocol/tls.py` |
| **Cluster** | Membership, routing, discovery | `cluster/gossip.py`, `cluster/consistent_hash.py` |
| **Resilience** | Fault tolerance, overload protection | `resilience/*.py` |
| **Compute** | CPU-bound task execution | `compute/worker_pool.py` |
| **Consistency** | Causal ordering, conflict resolution | `consistency/crdt/*.py` |
| **Storage** | Persistent state, cold starts | `storage/etcd_client.py` |
| **Metrics** | Observability, alerting | `metrics/prometheus.py` |

### 1.2 The Asyncio + Multiprocessing Pattern

Python's Global Interpreter Lock (GIL) prevents true thread parallelism. Our solution:

```
┌─────────────────────────────────────────┐
│         Asyncio Event Loop              │
│  (Single Thread, Handles 10K+ Conn)     │
│                                         │
│  TCP Server → Deserialize → Route       │
│       ↓                                 │
│  [I/O Bound] → Asyncio coroutine       │
│  [CPU Bound] → ProcessPoolExecutor     │
│       ↓                                 │
│  Serialize → TCP Send                   │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│      Process Pool (N workers)           │
│  Worker 1: SHA256 hashing               │
│  Worker 2: Large dataset sort           │
│  Worker 3: Metrics aggregation          │
│  Worker 4: CRDT merge                   │
└─────────────────────────────────────────┘
```

**Why this works:**
- Asyncio handles network I/O without blocking
- Processes bypass GIL for CPU-intensive work
- `ProcessPoolExecutor` reuses processes (no fork overhead per request)
- Semaphore prevents overwhelming the pool

---

## 2. Protocol Design

### 2.1 Binary Framing

Unlike text protocols (HTTP/JSON), our binary protocol:
- **No parsing ambiguity** — fixed-size headers
- **No delimiter scanning** — length-prefixed fields
- **Compact** — ~19 bytes overhead vs 100s for HTTP
- **Fast** — `struct.unpack` in C vs JSON parsing in Python

### 2.2 Vector Clock Integration

Every message carries a vector clock enabling **causal consistency**:

```
Message A (node-0): VC(node-0:1)
Message B (node-1): VC(node-1:1)
Message C (node-0): VC(node-0:2)

Causality:
  A → C (A happened before C)
  A || B (concurrent)
  B || C (concurrent)
```

**Conflict detection:**
```python
if local_vc.is_concurrent_with(remote_vc):
    # Same key updated concurrently
    # Resolve via CRDT merge
    crdt.merge(remote_state)
else:
    # Causally ordered — simple overwrite
    local_state = remote_state
```

---

## 3. Fault Tolerance Architecture

### 3.1 Failure Modes & Mitigations

| Failure Mode | Detection | Mitigation | Recovery |
|-------------|-----------|------------|----------|
| Node crash | Gossip timeout (15s) | Remove from hash ring | Auto when restarted |
| Network partition | Health check timeout | Circuit breaker OPEN | Rejoin on partition heal |
| Slow node | Latency p99 spike | Backpressure rejection | Auto when latency drops |
| Byzantine node | mTLS cert validation | Reject connection | Manual cert revocation |
| etcd unavailable | Connection timeout | Degrade to in-memory | Retry with backoff |

### 3.2 Circuit Breaker State Machine

```
                    ┌─────────┐
         ┌─────────│  CLOSED │◄────────┐
         │         └────┬────┘         │
         │    3 failures│              │ 2 successes
         │              ▼              │
         │         ┌─────────┐         │
         └────────►│  OPEN   │─────────┘
                   └────┬────┘
                        │ 8s timeout
                        ▼
                   ┌─────────┐
                   │HALF_OPEN│
                   └────┬────┘
                        │ 1 failure
                        └────────► OPEN
```

---

## 4. Consistency Model

### 4.1 Causal Consistency with CRDTs

The system provides **causal consistency** (weaker than strong consistency, stronger than eventual):

```
Alice posts "Hello" → Bob sees "Hello" → Bob replies "Hi"

Guarantee: If Bob saw Alice's message, all nodes will see Alice's 
message before Bob's reply (causal ordering preserved).

No guarantee: Two concurrent posts appear in same order on all nodes.
```

### 4.2 CRDT Selection Guide

| Data Type | CRDT | Conflict Resolution | Example |
|-----------|------|---------------------|---------|
| Counter (only +) | G-Counter | Max of each node's count | Page views |
| Counter (+/-) | PN-Counter | Two G-Counters | Bank balance |
| Single value | LWW-Register | Latest timestamp wins | User name |
| Set | OR-Set | Add-wins semantics | Shopping cart |
| Map | LWW-Map | Per-key LWW | User preferences |

---

## 5. Scalability Analysis

### 5.1 Horizontal Scaling

| Nodes | Gossip Complexity | Hash Ring Remapping | etcd Load |
|-------|------------------|---------------------|-----------|
| 3 | O(3) per cycle | 33% | Low |
| 10 | O(10) per cycle | 10% | Low |
| 100 | O(100) per cycle | 1% | Medium |
| 1000 | O(1000) per cycle | 0.1% | High |

**Bottleneck at 1000+ nodes:** Gossip becomes O(N). Solution: **Gossip subgroups** (nodes gossip within rack/region, aggregate across regions).

### 5.2 Vertical Scaling

| Resource | Limit | Mitigation |
|----------|-------|------------|
| File descriptors | 65K (ulimit) | Increase `ulimit -n`, connection pooling |
| Memory | RAM size | Backpressure, request shedding |
| CPU | 100% | ProcessPoolExecutor, horizontal scaling |
| Network | NIC bandwidth | Batch requests, compression |

---

## 6. Security Architecture

### 6.1 Threat Model

| Threat | Mitigation |
|--------|-----------|
| Eavesdropping | TLS 1.3 encryption |
| MITM | mTLS certificate verification |
| Replay attacks | Correlation IDs + timestamps |
| DoS | Backpressure + circuit breaker |
| Node impersonation | CA-signed certificates |

### 6.2 Certificate Lifecycle

```
Development: Self-signed CA (certs/generate.sh)
Staging:     Internal PKI
Production:  Let's Encrypt / Vault PKI
Rotation:    Automated via cert-manager
```

---

## 7. Deployment Patterns

### 7.1 Kubernetes (Recommended for Production)

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: distributed-node
spec:
  serviceName: dist-sys
  replicas: 3
  template:
    spec:
      containers:
      - name: node
        image: distributed-system:latest
        ports:
        - containerPort: 8000
        - containerPort: 9090  # Metrics
        env:
        - name: ETCD_ENDPOINTS
          value: "etcd-0.etcd:2379,etcd-1.etcd:2379,etcd-2.etcd:2379"
        - name: USE_TLS
          value: "true"
        volumeMounts:
        - name: certs
          mountPath: /app/certs
      volumes:
      - name: certs
        secret:
          secretName: tls-certs
```

### 7.2 Bare Metal

```bash
# Node 0
NODE_ID=node-0 NODE_PORT=8000 PEERS=host1:8001,host2:8002 \
  ETCD_ENDPOINTS=http://etcd:2379 USE_TLS=true \
  python -m src.main

# Node 1
NODE_ID=node-1 NODE_PORT=8001 PEERS=host0:8000,host2:8002 \
  ETCD_ENDPOINTS=http://etcd:2379 USE_TLS=true \
  python -m src.main
```

---

## 8. Performance Tuning

### 8.1 Checklist

- [ ] Enable `uvloop`: `pip install uvloop`
- [ ] Increase `ulimit -n 65535`
- [ ] Tune `ProcessPoolExecutor` workers: `max(2, cpu_count - 1)`
- [ ] Adjust backpressure `max_queue_depth` based on memory
- [ ] Enable TCP keepalive: `sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)`
- [ ] Use `SO_REUSEPORT` for multi-process load balancing (Linux)
- [ ] Compile protobuf: `protoc` generates C extensions
- [ ] Profile with `py-spy` or `austin` for hot paths

### 8.2 Benchmarking

```bash
# Install wrk or vegeta
wrk -t12 -c400 -d30s http://localhost:8000/health

# Or use Python client
python -c "
import asyncio
from src.client import DistributedClient

async def bench():
    client = DistributedClient(...)
    start = time.time()
    tasks = [client.request('echo', {'data': 'x'}) for _ in range(10000)]
    await asyncio.gather(*tasks)
    print(f'{(10000 / (time.time() - start)):.0f} req/s')

asyncio.run(bench())
"
```

