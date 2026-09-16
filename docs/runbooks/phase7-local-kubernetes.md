# Phase 7 local Kubernetes runbook

Prerequisites: Python 3.12, Docker, kind, kubectl, Helm, OpenSSL, Terraform.

```bash
python -m pip install -e '.[dev]'
python -m pytest tests/deployment -q
bash scripts/phase7/release_gate.sh
```

Manual lifecycle:

```bash
bash scripts/phase7/cluster_up.sh
PYTHONPATH=src python scripts/phase7/verify_cluster.py
PYTHONPATH=src python scripts/phase7/verify_persistence.py
bash scripts/phase7/verify_rollback.sh
bash scripts/phase7/cluster_down.sh
```

Cleanup is mandatory. `.phase7/tls` contains ephemeral private keys and is removed by `cluster_down.sh`.
