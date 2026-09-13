# Phase 5 cumulative release-gate hotfix v8

Apply this after the WSL network and release-gate hotfixes.

It fixes:

1. All six remaining `mypy` errors in `replication/service.py`,
   `replication/peer_client.py`, `crdt_service.py`, and `node.py`.
2. The restart smoke race where node 2 is reachable but correctly returns
   `RECOVERY_IN_PROGRESS` while durable reconciliation is still running.
3. It retains the earlier cross-key causal-session correction in
   `crdt_service.py`.
4. Incomplete peer frames are normalized to `CrdtPeerProtocolError` instead
   of leaking `asyncio.IncompleteReadError`.
5. The secure positive-flow read tolerates bounded WSL TLS startup resets.
6. Restart-smoke etcd membership results are explicitly typed and narrowed,
   resolving the remaining Pylance diagnostics.
7. Restart verification treats both `RECOVERY_IN_PROGRESS` (14) and
   `CAUSAL_UNAVAILABLE` (9) as transient while the bounded reconciliation
   deadline is active.
8. The crash-recovery smoke uses `SIGKILL` so the stopped node cannot keep
   renewing its etcd lease, and waits up to 20 seconds for TTL expiry.
9. Peer adapters depend on structural client protocols, allowing focused test
   doubles without Pylance argument-type errors.
10. Cluster peer cleanup ignores the benign OpenSSL
    `APPLICATION_DATA_AFTER_CLOSE_NOTIFY` shutdown error instead of masking the
    exchange timeout that caused it.
11. The Phase-5 launcher uses WSL-safe mTLS probe defaults (0.75-second direct,
    1.50-second indirect, 4-second suspicion) while keeping every value
    overridable through the environment.
12. The CRDT adapter test double uses the protocol's keyword-compatible
    `state` parameter name, removing the remaining Pylance diagnostics.
13. The restarted node now inherits the same WSL-safe cluster timeouts as the
    initially launched nodes, preventing false peer death during durable
    reconciliation.
14. Cluster bootstrap uses the request timeout rather than the short SWIM ping
    timeout, making TLS joins deterministic without weakening failure probes.
15. Durable CRDT requests received after the listener binds but before CRDT
    service creation return `RECOVERY_IN_PROGRESS`, not the false
    `CRDT mode is disabled` response.

```bash
cd ~/projects/distributed-system-phase1
source .venv/bin/activate
git switch phase/5-secure-persistence

rm -rf /tmp/phase5-final-release-gate-hotfix
mkdir -p /tmp/phase5-final-release-gate-hotfix

unzip -q \
  "/mnt/c/Users/HP/Downloads/phase5-cumulative-release-gate-hotfix-v8.zip" \
  -d /tmp/phase5-final-release-gate-hotfix

rsync -av \
  /tmp/phase5-final-release-gate-hotfix/phase5-final-release-gate-hotfix/ \
  ./
```

Format and verify:

```bash
python -m black \
  src/distsys/replication/service.py \
  src/distsys/replication/peer_client.py \
  src/distsys/cluster/peer_client.py \
  src/distsys/crdt_service.py \
  src/distsys/node.py \
  scripts/phase5_smoke.py \
  scripts/phase5_restart_smoke.py \
  tests/unit/test_peer_client.py

python -m ruff check --fix \
  src/distsys/replication/service.py \
  src/distsys/replication/peer_client.py \
  src/distsys/cluster/peer_client.py \
  src/distsys/crdt_service.py \
  src/distsys/node.py \
  scripts/phase5_smoke.py \
  scripts/phase5_restart_smoke.py \
  tests/unit/test_peer_client.py

python -m black \
  src/distsys/replication/service.py \
  src/distsys/replication/peer_client.py \
  src/distsys/cluster/peer_client.py \
  src/distsys/crdt_service.py \
  src/distsys/node.py \
  scripts/phase5_smoke.py \
  scripts/phase5_restart_smoke.py \
  tests/unit/test_peer_client.py

make quality
make phase5-etcd-integration
make phase5-secure-smoke
```

The restart loop retries only `CAUSAL_UNAVAILABLE` (9) and
`RECOVERY_IN_PROGRESS` (14) inside its bounded deadline. Any other remote CRDT
error still fails immediately.
