## Summary

Describe the change and the correctness or maintenance reason for it.

## Verification

- [ ] `make quality`
- [ ] Relevant distributed-behavior tests pass
- [ ] Security/image checks pass when applicable
- [ ] Kubernetes/Terraform verification updated when delivery behavior changes
- [ ] Documentation and verification evidence updated when claims change

## Correctness boundaries

- [ ] No new claim of linearizability, consensus, quorum durability, exactly-once execution, distributed ACID, Byzantine tolerance, multi-AZ HA, production SLOs, or multi-region DR
- [ ] Membership, ownership, causal consistency, and durability semantics remain accurately documented
- [ ] Telemetry does not become part of the correctness path
- [ ] Cloud mutation remains explicit, reviewed, reversible, and gated

## Operational impact

Describe any effect on persistence, mTLS identity, CRDT reconciliation, etcd coordination, observability, Helm, Kubernetes, Terraform, or teardown.
