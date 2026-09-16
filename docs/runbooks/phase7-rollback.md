# Phase 7 rollback runbook

The automated rollback gate upgrades the current release with an intentionally invalid readiness path. It must fail without a database schema change. The script then rolls back to the previous Helm revision, recreates the affected highest-ordinal pod, waits for StatefulSet recovery, and reruns the healthy CRDT/mTLS verifier.

```bash
bash scripts/phase7/verify_rollback.sh
```

A rollback is not successful until the post-rollback verifier exits zero.
