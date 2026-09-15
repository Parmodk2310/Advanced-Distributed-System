# Phase 7 rollback runbook

List revisions with `helm -n distsys history phase7`. Roll back using `helm -n distsys rollback phase7 REVISION --wait --timeout 5m`, then run `make phase7-local-verify`. The automated local gate creates a non-destructive unhealthy revision, requires its rollout to fail, restores the previous revision, and reruns the verifier.

Rollback does not reverse incompatible database migrations. Phase 7 introduces no database schema migration; future schema changes require a separate forward/backward compatibility plan and backup test.
