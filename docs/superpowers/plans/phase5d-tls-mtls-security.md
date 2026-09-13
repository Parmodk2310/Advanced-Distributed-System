# Phase 5D TLS 1.3 and mTLS Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect the existing framed TCP protocol with TLS 1.3, require mutual certificates in secure mode, and bind peer certificates to logical cluster node identities.

**Architecture:** Use Python's stdlib `ssl` only. Server/client SSL contexts are built once from settings; peer clients know the expected node id and verify DNS SAN identity after handshake, while inbound peer/control messages verify `Message.sender_id` against the authenticated certificate before dispatch.

**Tech Stack:** Python 3.12 ssl, OpenSSL CLI for development PKI, asyncio streams, pytest.

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

## File Map

Create:

```text
src/distsys/security/
├── __init__.py
├── errors.py
├── certificate.py
├── identity.py
└── tls_context.py

scripts/generate_dev_certs.sh

tests/unit/security/
├── __init__.py
├── test_certificate.py
├── test_identity.py
└── test_tls_context.py
```

Modify:

```text
src/distsys/utils/config.py
.env.example
.gitignore
src/distsys/cluster/peer_client.py
src/distsys/replication/peer_client.py
src/distsys/client.py
src/distsys/crdt_client.py
src/distsys/node.py
```

Integration tests:

```text
tests/integration/test_mtls_valid_peer.py
tests/integration/test_mtls_unknown_ca.py
tests/integration/test_mtls_identity_mismatch.py
tests/integration/test_tls_plaintext_rejected.py
```

### Task 1: TLS settings and SSL context factory

**Files:**
- Create: `src/distsys/security/errors.py`
- Create: `src/distsys/security/tls_context.py`
- Modify: `src/distsys/utils/config.py`
- Test: `tests/unit/security/test_tls_context.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- `TlsConfigurationError`
- `build_server_context(settings) -> ssl.SSLContext | None`
- `build_client_context(settings) -> ssl.SSLContext | None`
- Settings:
  - `tls_enabled=False`
  - `mtls_required=False`
  - `tls_ca_file=""`
  - `tls_cert_file=""`
  - `tls_key_file=""`
  - `tls_min_version="TLSv1.3"`

- [ ] **Step 1: Write disabled-mode test**

Both builders return `None` when TLS disabled.

- [ ] **Step 2: Write TLS 1.3 context test**

With temp CA/cert/key fixture, assert:

```python
assert context.minimum_version is ssl.TLSVersion.TLSv1_3
```

- [ ] **Step 3: Write config validation tests**

Reject:
- `MTLS_REQUIRED=true` with TLS false,
- TLS true with missing CA/cert/key,
- min version other than TLSv1.3 in Phase-5 secure profile.

- [ ] **Step 4: Verify RED**
- [ ] **Step 5: Implement server context**

Use:
- `ssl.PROTOCOL_TLS_SERVER`,
- `minimum_version=TLSv1_3`,
- `load_cert_chain`,
- `load_verify_locations`,
- `verify_mode=CERT_REQUIRED` when mTLS required.

- [ ] **Step 6: Implement client context**

Use `ssl.create_default_context(Purpose.SERVER_AUTH)`, CA file, optional client cert/key, TLS 1.3 minimum.

- [ ] **Step 7: Run and commit**

```bash
python -m pytest -q tests/unit/security/test_tls_context.py tests/unit/test_config.py
git add src/distsys/security src/distsys/utils/config.py tests
git commit -m "feat: build tls13 mutual authentication contexts"
```

### Task 2: Certificate SAN extraction and logical node identity verification

**Files:**
- Create: `src/distsys/security/certificate.py`
- Create: `src/distsys/security/identity.py`
- Test: `tests/unit/security/test_certificate.py`
- Test: `tests/unit/security/test_identity.py`

**Interfaces:**
- `dns_sans(cert: Mapping[str, object]) -> frozenset[str]`
- `ip_sans(cert) -> frozenset[str]`
- `verify_node_identity(cert, expected_node_id) -> None`
- `TlsPeerIdentityError`

- [ ] **Step 1: Write DNS SAN extraction test**
- [ ] **Step 2: Write matching identity test**
- [ ] **Step 3: Write wrong-node identity rejection test**
- [ ] **Step 4: Implement exact SAN comparison**

Do not accept Common Name as a fallback for logical node identity.

- [ ] **Step 5: Run and commit**

```bash
python -m pytest -q tests/unit/security/test_certificate.py tests/unit/security/test_identity.py
git add src/distsys/security tests/unit/security
git commit -m "feat: verify tls peer node identities"
```

### Task 3: Development PKI generation

**Files:**
- Create: `scripts/generate_dev_certs.sh`
- Modify: `.gitignore`

**Interfaces:**
- Generates under `certs/generated/`:
  - CA,
  - node-0,
  - node-1,
  - node-2,
  - `crdt-client` development credential.
- Node cert DNS SAN equals logical node id; IP SAN includes `127.0.0.1`.

- [ ] **Step 1: Implement idempotent shell script with `set -euo pipefail`**
- [ ] **Step 2: Generate**

```bash
rm -rf certs/generated
bash scripts/generate_dev_certs.sh
```

- [ ] **Step 3: Verify SANs**

```bash
openssl x509 -in certs/generated/node-1/node.crt -noout -text \
  | grep -A1 "Subject Alternative Name"
```

Expected: `DNS:node-1` and `IP Address:127.0.0.1`.

- [ ] **Step 4: Verify key files ignored**

```bash
git check-ignore certs/generated/node-1/node.key
```

Expected: exit 0.

- [ ] **Step 5: Commit script only**

```bash
git add scripts/generate_dev_certs.sh .gitignore
git commit -m "test: add development mtls certificate generator"
```

### Task 4: Secure cluster PeerClient outbound transport

**Files:**
- Modify: `src/distsys/cluster/peer_client.py`
- Test: `tests/unit/test_peer_client.py`

**Interfaces:**
- Constructor optional `ssl_context: ssl.SSLContext | None`.
- `_exchange_endpoint(..., expected_node_id: str | None = None)`.
- For known peers, `server_hostname=peer.node_id`.
- Secure `join` requires identity-aware seed (`SeedAddress.node_id`) or rejects before connection.

- [ ] **Step 1: Write open_connection argument test**

Monkeypatch `asyncio.open_connection`; known peer must receive:

```python
ssl=client_context
server_hostname="node-1"
```

- [ ] **Step 2: Write secure anonymous-seed rejection**

TLS enabled + `SeedAddress(node_id=None)` must raise `TlsPeerIdentityError`.

- [ ] **Step 3: Implement certificate extraction from writer**

After handshake:

```python
ssl_object = writer.get_extra_info("ssl_object")
cert = ssl_object.getpeercert()
verify_node_identity(cert, expected_node_id)
```

- [ ] **Step 4: Run existing peer-client tests plus new tests**
- [ ] **Step 5: Commit**

```bash
git add src/distsys/cluster/peer_client.py tests/unit/test_peer_client.py
git commit -m "feat: secure cluster peer connections"
```

### Task 5: Secure CRDT replication PeerClient outbound transport

**Files:**
- Modify: `src/distsys/replication/peer_client.py`
- Test: `tests/unit/test_crdt_peer_client.py`

**Interfaces:**
- Same TLS context injection pattern.
- Every `ClusterMember` call uses expected member node id for SNI/logical SAN verification.

- [ ] **Step 1: Write secure connection argument test**
- [ ] **Step 2: Write identity mismatch propagation test**
- [ ] **Step 3: Implement using shared security helper**
- [ ] **Step 4: Run and commit**

```bash
python -m pytest -q tests/unit/test_crdt_peer_client.py
git add src/distsys/replication/peer_client.py tests/unit/test_crdt_peer_client.py
git commit -m "feat: secure crdt replication transport"
```

### Task 6: TLS support for public TaskClient and CrdtClient

**Files:**
- Modify: `src/distsys/client.py`
- Modify: `src/distsys/crdt_client.py`
- Test: `tests/unit/test_codec.py` or new `tests/unit/test_clients_tls.py`

**Interfaces:**
- Client constructors accept:
  - `ssl_context: ssl.SSLContext | None = None`
  - `server_hostname: str | None = None`
- Plain compatibility remains unchanged when context is None.

- [ ] **Step 1: Write TaskClient TLS open_connection test**
- [ ] **Step 2: Write CrdtClient TLS open_connection test**
- [ ] **Step 3: Implement without altering causal token behavior**
- [ ] **Step 4: Run client/unit tests**
- [ ] **Step 5: Commit**

```bash
git add src/distsys/client.py src/distsys/crdt_client.py tests/unit/test_clients_tls.py
git commit -m "feat: support tls application clients"
```

### Task 7: TLS server listener and inbound peer identity enforcement

**Files:**
- Modify: `src/distsys/node.py`
- Test: `tests/integration/test_mtls_valid_peer.py`
- Test: `tests/integration/test_mtls_identity_mismatch.py`

**Interfaces:**
- `DistributedNode` builds/accepts server SSL context.
- `asyncio.start_server(..., ssl=server_context)`.
- In secure mode, every peer/control message requiring node identity is checked before dispatch.

Peer-identity-required categories:
- JOIN_REQUEST,
- PING,
- PING_REQ,
- GOSSIP,
- FORWARDED_REQUEST,
- CRDT_REPLICATE,
- CRDT_FETCH,
- CRDT_DIGEST,
- forwarded CRDT_MUTATE_REQUEST,
- forwarded CRDT_READ_REQUEST.

Direct client CRDT/task requests require a valid mTLS cert when server is configured `CERT_REQUIRED`, but their certificate SAN is not treated as application authorization.

- [ ] **Step 1: Write valid secure peer test**
- [ ] **Step 2: Write wrong-node sender test**

Connect using node-2 cert but send peer message `sender_id="node-1"`; expect connection/structured rejection and no membership/state mutation.

- [ ] **Step 3: Implement `_verify_authenticated_sender(message, writer)`**

Use `writer.get_extra_info("ssl_object").getpeercert()` and logical identity verifier.

- [ ] **Step 4: Ensure plaintext mode bypasses verifier**
- [ ] **Step 5: Run and commit**

```bash
python -m pytest -q \
  tests/integration/test_mtls_valid_peer.py \
  tests/integration/test_mtls_identity_mismatch.py
git add src/distsys/node.py tests/integration
git commit -m "feat: authenticate inbound peer identities"
```

### Task 8: Unknown CA, missing cert, and plaintext rejection

**Files:**
- Create: `tests/integration/test_mtls_unknown_ca.py`
- Create: `tests/integration/test_tls_plaintext_rejected.py`

**Interfaces:**
- Full TCP/TLS handshake behavior.

- [ ] **Step 1: Unknown-CA test**

Start secure node using dev CA; client context trusts a different generated CA; assert handshake fails.

- [ ] **Step 2: Missing-client-certificate test**

Server mTLS required; client trusts CA but presents no client certificate; assert handshake fails.

- [ ] **Step 3: Plaintext test**

Use `asyncio.open_connection` without SSL to secure listener; write a normal frame; assert no valid application response and connection closes.

- [ ] **Step 4: Run complete TLS integration gate**

```bash
python -m pytest -q \
  tests/integration/test_mtls_valid_peer.py \
  tests/integration/test_mtls_unknown_ca.py \
  tests/integration/test_mtls_identity_mismatch.py \
  tests/integration/test_tls_plaintext_rejected.py
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_mtls_unknown_ca.py tests/integration/test_tls_plaintext_rejected.py
git commit -m "test: verify phase five tls rejection paths"
```
