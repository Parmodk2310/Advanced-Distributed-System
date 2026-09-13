# Phase 5C etcd Coordination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add etcd-backed member registration, lease renewal, discovery bootstrap, and degraded/recovery behavior without making the CRDT data plane depend on etcd.

**Architecture:** Use `etcd3gw>=2.7,<3` behind a project-owned `CoordinationClient` protocol. The library is blocking, so every call crosses `asyncio.to_thread`; unit tests use a fake client, while integration tests use one pinned local etcd container.

**Tech Stack:** Python 3.12+, etcd3gw 2.7.x, asyncio, canonical JSON, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-phase5-secure-persistence-design.md`

## Global Constraints

- Baseline release is `v0.4.0` at merge commit `e6cf2d52df49b6548ddfdd70aa0a212f69747dac`.
- Work only on branch `phase/5-secure-persistence`.
- Python remains `>=3.12`.
- Protobuf remains the application wire format.
- Existing `MessageType` numeric values `1..18` must not change.
- Existing `ErrorCode` numeric values `0..11` must not change.
- Phase-5 error codes append exactly: `12 PERSISTENCE_UNAVAILABLE`, `13 PERSISTENCE_BACKPRESSURE`, `14 RECOVERY_IN_PROGRESS`, `15 COORDINATION_UNAVAILABLE`, `16 TLS_AUTHENTICATION_FAILED`.
- `TLS_ENABLED=false` and `MTLS_REQUIRED=false` remain compatibility defaults; secure Phase-5 smoke enables both.
- Secure mode requires TLS 1.3 minimum.
- Persistence uses local SQLite with WAL and `synchronous=NORMAL` by default.
- A successful mutation is locally durable before ACK; it is not a quorum-durable ACK.
- etcd is coordination/discovery only; CRDT payloads never live in etcd.
- SWIM-lite remains the live membership/failure detector.
- Replication outbox remains in memory.
- Normal restart restores the durable causal actor/counter; SWIM incarnation still changes.
- CRDT classes remain storage/network independent.
- Blocking SQLite and etcd client calls must run off the asyncio event loop.
- New network tests use pytest-assigned explicit ports; do not add new direct `port=0` test fixtures.
- Generated certificates, private keys, SQLite DB/WAL/SHM files, and runtime logs must not be committed.
- Every production behavior follows TDD: failing test -> verify failure -> minimal implementation -> verify pass -> focused commit.

---

## Dependency Decision

Add:

```text
etcd3gw>=2.7,<3
```

The implementation uses the etcd v3 gRPC-gateway client API:

```python
Etcd3Client(...)
client.put(...)
client.get_prefix(...)
lease = client.lease(ttl=...)
lease.refresh()
```

No etcd-generated Protobuf client is added to this repository.

Pin local integration etcd image:

```text
quay.io/coreos/etcd:v3.6.14
```

## File Map

Create:

```text
src/distsys/coordination/
├── __init__.py
├── errors.py
├── models.py
├── client.py
├── etcd_client.py
├── lease.py
├── discovery.py
└── service.py

docker/etcd/docker-compose.yml

tests/unit/coordination/
├── __init__.py
├── fakes.py
├── test_models.py
├── test_etcd_client.py
├── test_lease.py
├── test_discovery.py
└── test_service.py
```

Modify:

```text
pyproject.toml
requirements.txt
src/distsys/utils/config.py
.env.example
src/distsys/cluster/member.py
```

Integration tests:

```text
tests/integration/test_etcd_registration.py
tests/integration/test_etcd_lease_expiry.py
tests/integration/test_etcd_outage.py
```

### Task 1: Coordination models, keys, and protocol

**Files:**
- Create: `src/distsys/coordination/errors.py`
- Create: `src/distsys/coordination/models.py`
- Create: `src/distsys/coordination/client.py`
- Test: `tests/unit/coordination/test_models.py`

**Interfaces:**
- `CoordinationUnavailableError`
- `LeaseHandle(lease_id: int, ttl_seconds: int)`
- `CoordinationMember`
- `CoordinationHealth`
- `member_key(namespace, node_id)`
- `node_metadata_key(namespace, node_id)`
- `CoordinationClient` protocol

`CoordinationMember` fields:

```python
node_id: str
node_uuid: str
host: str
port: int
membership_incarnation: int
protocol_version: int
release: str
tls_required: bool
```

- [ ] **Step 1: Write validation and canonical-JSON tests**
- [ ] **Step 2: Verify RED**
- [ ] **Step 3: Implement key paths under `/distsys/v1`**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/coordination/test_models.py
git add src/distsys/coordination tests/unit/coordination/test_models.py
git commit -m "feat: add coordination domain contract"
```

### Task 2: Add etcd3gw dependency and async adapter

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Create: `src/distsys/coordination/etcd_client.py`
- Test: `tests/unit/coordination/test_etcd_client.py`

**Interfaces:**
- `EtcdGatewayCoordinationClient(endpoints, namespace, timeout_seconds)`
- Async methods:
  - `connect`
  - `close`
  - `grant_lease`
  - `refresh_lease`
  - `register_member`
  - `put_node_metadata`
  - `discover_members`
  - `delete_member`

- [ ] **Step 1: Add dependency**

```toml
dependencies = [
  "protobuf>=4.25,<7",
  "etcd3gw>=2.7,<3",
]
```

Mirror it in `requirements.txt`.

- [ ] **Step 2: Write fake-etcd3gw adapter test**

Monkeypatch the factory with a blocking fake and record thread IDs. Assert `connect/status`, `put`, `get_prefix`, `lease`, and `lease.refresh` do not run on event-loop thread.

- [ ] **Step 3: Write endpoint failover test**

First fake endpoint raises connection error; second succeeds; client marks second active.

- [ ] **Step 4: Implement all blocking library calls through `asyncio.to_thread`**
- [ ] **Step 5: Normalize etcd errors into `CoordinationUnavailableError`**
- [ ] **Step 6: Run and commit**

```bash
python -m pytest -q tests/unit/coordination/test_etcd_client.py
git add pyproject.toml requirements.txt src/distsys/coordination/etcd_client.py tests/unit/coordination/test_etcd_client.py
git commit -m "feat: add async etcd gateway adapter"
```

### Task 3: LeaseManager

**Files:**
- Create: `src/distsys/coordination/lease.py`
- Test: `tests/unit/coordination/test_lease.py`

**Interfaces:**
- `LeaseManager(client, ttl_seconds=15, renew_interval_seconds=5)`
- `async start(member)`
- `async stop()`
- `health`
- callbacks:
  - `on_degraded`
  - `on_recovered`

**Behavior:**
- acquire lease,
- register member attached to lease,
- sleep renew interval,
- refresh,
- on refresh failure mark degraded and retry,
- on recovered connection obtain a fresh lease and re-register.

- [ ] **Step 1: Write normal refresh test using fake clock/sleeper**
- [ ] **Step 2: Write lease-loss then reacquire test**
- [ ] **Step 3: Write stop-cancels-task test**
- [ ] **Step 4: Verify RED**
- [ ] **Step 5: Implement one owned background task with bounded retry delay**
- [ ] **Step 6: Run and commit**

```bash
python -m pytest -q tests/unit/coordination/test_lease.py
git add src/distsys/coordination/lease.py tests/unit/coordination/test_lease.py
git commit -m "feat: manage etcd member leases"
```

### Task 4: Discovery service and secure seed identity

**Files:**
- Create: `src/distsys/coordination/discovery.py`
- Modify: `src/distsys/cluster/member.py`
- Test: `tests/unit/coordination/test_discovery.py`
- Test: `tests/unit/test_member.py`

**Interfaces:**
- Extend `SeedAddress` compatibly:

```python
@dataclass(frozen=True, slots=True)
class SeedAddress:
    host: str
    port: int
    node_id: str | None = None
```

Existing `"host:port"` parsing remains valid.

Add secure parse form:

```text
node-1@127.0.0.1:18001
```

- `DiscoveryService.discover_seeds(local_node_id) -> tuple[SeedAddress, ...]`

- [ ] **Step 1: Write legacy SeedAddress regression**
- [ ] **Step 2: Write secure seed parsing test**
- [ ] **Step 3: Write discovery filter test**

etcd members containing local node plus two peers must return only peers, sorted by node id, each with node_id populated.

- [ ] **Step 4: Implement**
- [ ] **Step 5: Run and commit**

```bash
python -m pytest -q tests/unit/test_member.py tests/unit/coordination/test_discovery.py
git add src/distsys/cluster/member.py src/distsys/coordination/discovery.py tests
git commit -m "feat: discover identity aware cluster seeds"
```

### Task 5: CoordinationService facade

**Files:**
- Create: `src/distsys/coordination/service.py`
- Test: `tests/unit/coordination/test_service.py`

**Interfaces:**
- `CoordinationService(client, discovery, lease_manager)`
- `async bootstrap(member) -> tuple[SeedAddress, ...]`
- `async start_lease(member)`
- `async stop()`
- `health`

- [ ] **Step 1: Write bootstrap-order test**

Expected events:

```text
connect
put durable node metadata
discover members
grant lease/register member
```

- [ ] **Step 2: Write post-start degradation test**

Lease refresh failure changes health to degraded but does not raise into caller after `start_lease`.

- [ ] **Step 3: Implement facade**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/coordination/test_service.py
git add src/distsys/coordination/service.py tests/unit/coordination/test_service.py
git commit -m "feat: coordinate etcd discovery and leases"
```

### Task 6: etcd settings

**Files:**
- Modify: `src/distsys/utils/config.py`
- Modify: `.env.example`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- `etcd_enabled=True`
- `etcd_endpoints=("http://127.0.0.1:2379",)`
- `etcd_namespace="/distsys/v1"`
- `etcd_lease_ttl_seconds=15`
- `etcd_renew_interval_seconds=5`

- [ ] **Step 1: Add comma-separated endpoint parser tests**
- [ ] **Step 2: Add `renew >= ttl` rejection test**
- [ ] **Step 3: Add empty namespace/endpoint validation**
- [ ] **Step 4: Implement env parsing**
- [ ] **Step 5: Run and commit**

```bash
python -m pytest -q tests/unit/test_config.py
git add src/distsys/utils/config.py .env.example tests/unit/test_config.py
git commit -m "feat: configure etcd coordination"
```

### Task 7: Local etcd Docker topology

**Files:**
- Create: `docker/etcd/docker-compose.yml`
- Test: manual/integration preflight in `tests/integration/test_etcd_registration.py`

**Interfaces:**
- One etcd service
- loopback-published client port `2379`
- data volume scoped to compose project
- health check using `etcdctl endpoint health`

- [ ] **Step 1: Create compose file pinned to `quay.io/coreos/etcd:v3.6.14`**
- [ ] **Step 2: Start**

```bash
docker compose -f docker/etcd/docker-compose.yml up -d
docker compose -f docker/etcd/docker-compose.yml ps
```

- [ ] **Step 3: Verify**

```bash
docker compose -f docker/etcd/docker-compose.yml exec -T etcd \
  etcdctl endpoint health
```

Expected: healthy.

- [ ] **Step 4: Commit**

```bash
git add docker/etcd/docker-compose.yml
git commit -m "test: add local etcd integration topology"
```

### Task 8: Real etcd registration and lease expiry integration

**Files:**
- Create: `tests/integration/test_etcd_registration.py`
- Create: `tests/integration/test_etcd_lease_expiry.py`

**Interfaces:**
- Uses actual `EtcdGatewayCoordinationClient`.

- [ ] **Step 1: Registration test**

Create member, register with short lease, discover it, assert all serialized fields.

- [ ] **Step 2: Lease expiry test**

TTL=2 seconds, do not refresh, poll discovery until member disappears within bounded timeout.

- [ ] **Step 3: Run**

```bash
python -m pytest -q \
  tests/integration/test_etcd_registration.py \
  tests/integration/test_etcd_lease_expiry.py
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_etcd_registration.py tests/integration/test_etcd_lease_expiry.py
git commit -m "test: verify etcd registration and lease expiry"
```

### Task 9: Post-start etcd outage/recovery integration

**Files:**
- Create: `tests/integration/test_etcd_outage.py`

**Interfaces:**
- Tests `LeaseManager`/`CoordinationService`, not full node orchestration yet.

- [ ] **Step 1: Start coordination and verify healthy**
- [ ] **Step 2: Stop etcd container**
- [ ] **Step 3: Wait for health to become degraded**
- [ ] **Step 4: Restart etcd**
- [ ] **Step 5: Wait for new lease/member registration**
- [ ] **Step 6: Assert service recovers without changing member identity**
- [ ] **Step 7: Run and commit**

```bash
python -m pytest -q tests/integration/test_etcd_outage.py
git add tests/integration/test_etcd_outage.py
git commit -m "test: verify etcd coordination recovery"
```
