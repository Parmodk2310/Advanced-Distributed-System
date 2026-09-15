import importlib.util
from pathlib import Path

import pytest

from distsys.causal import CausalToken, VersionVector
from distsys.crdt import CrdtType
from distsys.crdt_client import CrdtResult, RemoteCrdtError


def load_phase5_smoke():
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase5_smoke.py"
    spec = importlib.util.spec_from_file_location("phase5_smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_phase5_restart_smoke():
    path = Path(__file__).resolve().parents[2] / "scripts" / "phase5_restart_smoke.py"
    spec = importlib.util.spec_from_file_location("phase5_restart_smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_restart_retry_accepts_only_transient_rejoin_errors():
    module = load_phase5_restart_smoke()

    assert module.is_transient_rejoin_error(14)
    assert module.is_transient_rejoin_error(9)
    assert not module.is_transient_rejoin_error(12)


def test_restarted_node_uses_wsl_safe_cluster_timeouts(tmp_path, monkeypatch):
    module = load_phase5_restart_smoke()
    monkeypatch.delenv("CLUSTER_PING_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("CLUSTER_INDIRECT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("CLUSTER_SUSPICION_TIMEOUT_SECONDS", raising=False)

    env = module.node_env(tmp_path, tmp_path, tmp_path, "node-2", 18002)

    assert env["CLUSTER_PING_TIMEOUT_SECONDS"] == "0.75"
    assert env["CLUSTER_INDIRECT_TIMEOUT_SECONDS"] == "1.50"
    assert env["CLUSTER_SUSPICION_TIMEOUT_SECONDS"] == "4.0"


@pytest.mark.asyncio
async def test_secure_read_retries_connection_reset_then_succeeds():
    module = load_phase5_smoke()
    token = CausalToken(VersionVector())
    expected = CrdtResult("key", CrdtType.GCOUNTER, 2, token, "node-2", False)

    class Reader:
        def __init__(self):
            self.attempts = 0

        async def read(self, key, *, causal_token):
            self.attempts += 1
            if self.attempts == 1:
                raise ConnectionResetError("transient WSL reset")
            return expected

    reader = Reader()
    result = await module.read_when_ready(
        reader,
        "key",
        causal_token=token,
        timeout_seconds=1.0,
    )

    assert result is expected
    assert reader.attempts == 2


@pytest.mark.asyncio
async def test_secure_read_does_not_hide_non_recovery_remote_error():
    module = load_phase5_smoke()

    class Reader:
        async def read(self, key, *, causal_token):
            raise RemoteCrdtError(12, "persistence unavailable")

    with pytest.raises(RemoteCrdtError, match="persistence unavailable"):
        await module.read_when_ready(
            Reader(),
            "key",
            causal_token=CausalToken(VersionVector()),
            timeout_seconds=1.0,
        )
