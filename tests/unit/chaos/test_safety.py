import json
from pathlib import Path

import pytest

from distsys.chaos.safety import (
    ManagedManifest,
    require_chaos_opt_in,
    validate_duration,
    validate_pid,
)


def test_opt_in_is_mandatory(monkeypatch):
    monkeypatch.delenv("RUN_CHAOS_TESTS", raising=False)
    with pytest.raises(PermissionError):
        require_chaos_opt_in()
    monkeypatch.setenv("RUN_CHAOS_TESTS", "1")
    require_chaos_opt_in()


def test_manifest_and_duration_reject_unmanaged_targets(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "runtime_dir": str(tmp_path),
                "pids": {
                    "node-0": {
                        "pid": 123,
                        "start_token": "x",
                        "cmdline_contains": "distsys.main",
                    }
                },
                "proxies": ["peer-node-0"],
                "services": ["etcd"],
            }
        )
    )
    manifest = ManagedManifest.load(path)
    assert manifest.has_proxy("peer-node-0")
    assert manifest.has_service("etcd")
    with pytest.raises(ValueError):
        validate_duration(31, maximum_seconds=30)
    with pytest.raises(ValueError):
        validate_pid(456, manifest)
