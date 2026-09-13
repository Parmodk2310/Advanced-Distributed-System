# Phase 5 File Manifest

This manifest lists the exact files added or changed by the Phase-5 package relative to the corrected `v0.4.0` baseline used for packaging.

**Changed/new files:** 115

## Persistence

```text
src/distsys/persistence/__init__.py
src/distsys/persistence/backup.py
src/distsys/persistence/codec.py
src/distsys/persistence/durable_store.py
src/distsys/persistence/errors.py
src/distsys/persistence/executor.py
src/distsys/persistence/migrations.py
src/distsys/persistence/models.py
src/distsys/persistence/repository.py
src/distsys/persistence/sqlite_repository.py
```

## Coordination and etcd

```text
docker/etcd/docker-compose.yml
src/distsys/coordination/__init__.py
src/distsys/coordination/client.py
src/distsys/coordination/discovery.py
src/distsys/coordination/errors.py
src/distsys/coordination/etcd_client.py
src/distsys/coordination/lease.py
src/distsys/coordination/models.py
src/distsys/coordination/service.py
```

## Security and PKI

```text
scripts/generate_dev_certs.sh
src/distsys/security/__init__.py
src/distsys/security/certificate.py
src/distsys/security/errors.py
src/distsys/security/identity.py
src/distsys/security/tls_context.py
```

## Recovery and health

```text
src/distsys/health/__init__.py
src/distsys/health/state.py
src/distsys/recovery/__init__.py
src/distsys/recovery/coordinator.py
src/distsys/recovery/reconciliation.py
src/distsys/recovery/restore.py
```

## Core Phase-5 integration changes

```text
src/distsys/causal/clock.py
src/distsys/client.py
src/distsys/cluster/member.py
src/distsys/cluster/peer_client.py
src/distsys/cluster/service.py
src/distsys/crdt_client.py
src/distsys/crdt_service.py
src/distsys/node.py
src/distsys/proto/messages_pb2.py
src/distsys/proto/messages_pb2.pyi
src/distsys/replication/anti_entropy.py
src/distsys/replication/causal_repair.py
src/distsys/replication/peer_client.py
src/distsys/replication/service.py
src/distsys/storage/__init__.py
src/distsys/storage/crdt_store.py
src/distsys/storage/protocol.py
src/distsys/utils/config.py
```

## Protocol and configuration

```text
.env.example
.gitignore
Makefile
proto/messages.proto
pyproject.toml
requirements.txt
```

## Runtime and verification scripts

```text
scripts/phase5_etcd_smoke.py
scripts/phase5_restart_smoke.py
scripts/phase5_smoke.py
scripts/phase5_verify.sh
scripts/run_phase5_cluster.sh
```

## Unit tests

```text
tests/unit/coordination/__init__.py
tests/unit/coordination/fakes.py
tests/unit/coordination/test_discovery.py
tests/unit/coordination/test_etcd_client.py
tests/unit/coordination/test_lease.py
tests/unit/coordination/test_models.py
tests/unit/coordination/test_service.py
tests/unit/health/__init__.py
tests/unit/health/test_state.py
tests/unit/persistence/__init__.py
tests/unit/persistence/test_backup.py
tests/unit/persistence/test_codec.py
tests/unit/persistence/test_durable_store.py
tests/unit/persistence/test_executor.py
tests/unit/persistence/test_migrations.py
tests/unit/persistence/test_models.py
tests/unit/persistence/test_sqlite_repository.py
tests/unit/recovery/__init__.py
tests/unit/recovery/test_coordinator.py
tests/unit/recovery/test_reconciliation.py
tests/unit/recovery/test_restore.py
tests/unit/security/__init__.py
tests/unit/security/test_certificate.py
tests/unit/security/test_identity.py
tests/unit/security/test_tls_context.py
tests/unit/test_causal_clock.py
tests/unit/test_clients_tls.py
tests/unit/test_cluster_service.py
tests/unit/test_config.py
tests/unit/test_crdt_peer_client.py
tests/unit/test_member.py
tests/unit/test_message.py
tests/unit/test_peer_client.py
tests/unit/test_replication_service.py
```

## Integration tests

```text
tests/integration/cluster_helpers.py
tests/integration/etcd_helpers.py
tests/integration/test_coordination_health.py
tests/integration/test_crdt_local_operations.py
tests/integration/test_durable_crdt_restart.py
tests/integration/test_etcd_lease_expiry.py
tests/integration/test_etcd_outage.py
tests/integration/test_etcd_registration.py
tests/integration/test_mtls_cluster_replication.py
tests/integration/test_mtls_identity_mismatch.py
tests/integration/test_mtls_unknown_ca.py
tests/integration/test_mtls_valid_peer.py
tests/integration/test_recovery_readiness.py
tests/integration/test_replica_recovery_reconciliation.py
tests/integration/test_tls_plaintext_rejected.py
tests/integration/tls_helpers.py
```

## Documentation and application guide

```text
APPLY_PHASE5.md
README.md
docs/PHASE5_FILE_MANIFEST.md
docs/PHASE5_VERIFICATION.md
docs/PHASES.md
```

No Phase-4 baseline files are deleted by the overlay. Runtime SQLite files, generated certificates/private keys, caches, and logs are intentionally excluded.
