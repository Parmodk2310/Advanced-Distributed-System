# Phase 5 WSL Hotfix

Apply from the repository root on `phase/5-secure-persistence`:

```bash
rm -rf /tmp/phase5-wsl-hotfix
mkdir -p /tmp/phase5-wsl-hotfix
unzip -q "/mnt/c/Users/HP/Downloads/phase5-wsl-hotfix.zip" -d /tmp/phase5-wsl-hotfix
rsync -av /tmp/phase5-wsl-hotfix/phase5-wsl-hotfix/ ./

python -m black src tests scripts
python -m ruff check --fix src tests scripts
python -m black src tests scripts

python -m pytest -q \
  tests/unit/test_peer_client.py \
  tests/unit/test_crdt_peer_client.py \
  tests/integration/test_crdt_node_rejoin.py \
  tests/integration/test_single_node.py::test_multiple_clients \
  tests/integration/test_single_node.py::test_clean_stop

make quality
PYTHONPATH=src python -m compileall -q src scripts tests
```

Expected focused test result: 15 passed (or more if upstream tests have changed).

The Docker/etcd gates require a running Docker daemon and are intentionally separate from this code hotfix.
