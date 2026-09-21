# Documentation Guide

Advanced Distributed System is a completed seven-phase systems-engineering project. This index separates the fastest portfolio review path from the deeper engineering record.

## Recruiter / five-minute path

1. [Project README](../README.md) — problem, capabilities, verified results and scope boundaries.
2. [Phase 1–7 evolution](architecture/phase1-7-evolution.md) — how the runtime grows from a single node to verified delivery.
3. [Phase 7 verification ledger](verification/phase7.md) — local Kubernetes, temporary AWS EKS lifecycle and teardown evidence.
4. [v0.7.0 release notes](releases/v0.7.0.md) — immutable release identity, signing, SBOM and limitations.

## Senior engineer / deep-dive path

1. [Architecture index](architecture/README.md) — current architecture and rendered diagrams.
2. [Design records](design/) — detailed phase contracts, algorithms, trade-offs and non-goals.
3. [Verification records](verification/) — reproducible evidence and historical phase gates.
4. [Runbooks](runbooks/) — local Kubernetes, AWS demonstration, rollback, security and secrets.
5. [Release record](releases/v0.7.0.md) — formal release evidence.

## Documentation status model

Documentation falls into three categories:

| Category | Purpose |
| --- | --- |
| **Current architecture** | Describes the implemented Phase 1–7 system as it exists now. |
| **Historical design / verification record** | Preserves decisions and milestone gates from development. Historical planning language is retained for traceability and is not unfinished current work. |
| **Release evidence** | Immutable evidence associated with a specific release, commit, workflow run or image digest. |

The current project status is defined by the root README, current architecture pages, protected-`main` CI, and formal release evidence. Historical test counts and planning metadata should not be interpreted as the latest `main` state.

## Directory map

```text
docs/
├── README.md          # this reviewer guide
├── architecture/      # current architecture and rendered diagrams
├── design/            # detailed engineering design records
├── verification/      # phase evidence and verification ledgers
├── runbooks/          # operational procedures
├── releases/          # formal release notes and identities
└── history/           # documentation/process history retained for traceability
```

## Scope boundaries

The project deliberately does not claim linearizability, consensus, quorum-durable acknowledgements, exactly-once distributed execution, distributed ACID transactions, Byzantine fault tolerance, multi-AZ availability, permanent hosting, production SLOs, internet-scale capacity or multi-region disaster recovery.

See the [root README](../README.md#scope-boundaries) for the concise current statement.
