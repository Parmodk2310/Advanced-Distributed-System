# Phase 3 Verification

> **Record status:** Historical milestone verification record. Phase 3 is implemented and verified in the completed seven-phase system. The measurements below are evidence from that phase milestone, not the latest cumulative `main` test count. See the [current phase architecture](../architecture/phase3-distributed-cluster.md).

Date: 2026-09-13

## Automated behavior verification in the generated package

Command:

```bash
PYTHONPATH=src python -m pytest -q
```

Observed result:

```text
125 passed in 4.43s
```

This includes the complete Phase-1/2 regression suite plus Phase-3 unit and integration tests.

## Bytecode / syntax verification

Command:

```bash
python -m compileall -q src scripts tests
```

Observed result:

```text
compileall OK
```

## Real three-node inspection smoke

The cluster runner was launched with three local nodes on ports 18000, 18001, and 18002, then the inspection smoke was executed.

Command:

```bash
PYTHONPATH=src python scripts/phase3_smoke.py \
  --host 127.0.0.1 \
  --ports 18000 18001 18002
```

Observed result:

```text
endpoints_reachable=3/3
membership_converged=3/3 ALIVE on every snapshot
routing_key=phase3-smoke-0
calculated_owner=node-1
sample_key_owners=node-0,node-1,node-2
remote_routed_execution=PASS
phase3_smoke=PASS
```

After the runner was terminated:

```text
phase3_ports_free=PASS
```

## Managed failure / failover / rejoin smoke

Command:

```bash
PYTHONPATH=src python scripts/phase3_smoke.py \
  --host 127.0.0.1 \
  --ports 18000 18001 18002 \
  --managed-command "bash scripts/run_phase3_cluster.sh"
```

Observed result:

```text
managed_failure_detection=PASS
managed_failover=PASS
managed_rejoin=PASS
```

## Quality tooling

The artifact-generation environment does not have Ruff, Black, or mypy installed. Those commands are therefore intentionally **not** recorded as passing here. The target WSL development environment already has those tools and must run the authoritative gate:

```bash
make proto
make quality
```

Do not tag `v0.3.0` until pytest, Ruff, Black, and mypy all pass on the user's Phase-3 branch and again after merge to `main`.

## Performance note

The Phase-3 smoke is a correctness, convergence, routing, and failover validation. It is not a throughput or latency benchmark. Formal benchmark claims remain Phase 6 work.
