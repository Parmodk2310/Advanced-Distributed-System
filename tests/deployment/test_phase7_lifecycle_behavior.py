import asyncio
import importlib.util
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERIFIER_PATH = ROOT / "scripts" / "phase7" / "verify_public_endpoint.py"
EBS_WAITER = ROOT / "scripts" / "phase7" / "wait_for_ebs_deletion.sh"


def load_verifier():
    spec = importlib.util.spec_from_file_location("phase7_public_verifier", VERIFIER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_endpoint_readiness_recovers_after_delayed_dns(monkeypatch) -> None:
    verifier = load_verifier()
    real_getaddrinfo = socket.getaddrinfo
    attempts = 0

    def delayed_getaddrinfo(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise socket.gaierror(socket.EAI_AGAIN, "temporary DNS failure")
        return real_getaddrinfo(*args, **kwargs)

    monkeypatch.setattr(verifier.socket, "getaddrinfo", delayed_getaddrinfo)
    server = await asyncio.start_server(lambda _reader, writer: writer.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        await verifier.wait_for_endpoint(
            "127.0.0.1",
            port,
            timeout_seconds=1,
            poll_interval=0.01,
        )
    finally:
        server.close()
        await server.wait_closed()

    assert attempts >= 2


@pytest.mark.asyncio
async def test_endpoint_readiness_timeout_reports_last_dns_error(monkeypatch) -> None:
    verifier = load_verifier()

    def unavailable_dns(*_args, **_kwargs):
        raise socket.gaierror(socket.EAI_NONAME, "name not known")

    monkeypatch.setattr(verifier.socket, "getaddrinfo", unavailable_dns)
    with pytest.raises(TimeoutError, match="public endpoint was not ready") as error:
        await verifier.wait_for_endpoint(
            "not-ready.invalid",
            8000,
            timeout_seconds=0.03,
            poll_interval=0.005,
        )

    assert "name not known" in str(error.value)


def write_fake_aws(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_aws = fake_bin / "aws"
    fake_aws.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" != "ec2 describe-volumes" ]]; then
  echo "unexpected fake AWS invocation: $*" >&2
  exit 99
fi
if [[ "${FAKE_EBS_MODE:-empty}" == "exists" ]]; then
  printf '%s\n' '[{"VolumeId":"vol-phase7","State":"available","Attachments":[]}]'
else
  printf '%s\n' '[]'
fi
""",
        encoding="utf-8",
    )
    fake_aws.chmod(0o755)
    return fake_bin


def run_ebs_waiter(tmp_path: Path, mode: str) -> subprocess.CompletedProcess[str]:
    fake_bin = write_fake_aws(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "AWS_REGION": "ap-south-1",
            "PHASE7_EBS_WAIT_TIMEOUT_SECONDS": "1",
            "PHASE7_EBS_WAIT_POLL_SECONDS": "1",
            "FAKE_EBS_MODE": mode,
        }
    )
    return subprocess.run(
        ["bash", str(EBS_WAITER)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )


def test_ebs_waiter_succeeds_when_no_tagged_volumes_remain(tmp_path: Path) -> None:
    result = run_ebs_waiter(tmp_path, "empty")

    assert result.returncode == 0, result.stderr
    assert '"ebs_convergence":"pass"' in result.stdout
    assert '"remaining_volumes":0' in result.stdout


def test_ebs_waiter_times_out_with_remaining_volume_diagnostics(tmp_path: Path) -> None:
    result = run_ebs_waiter(tmp_path, "exists")

    assert result.returncode == 1
    assert "timed out waiting for Phase 7 EBS volumes" in result.stderr
    assert "vol-phase7" in result.stderr


@pytest.mark.asyncio
async def test_endpoint_readiness_enforces_deadline_for_blocked_dns(monkeypatch) -> None:
    verifier = load_verifier()

    def blocked_dns(*_args, **_kwargs):
        time.sleep(0.2)
        raise socket.gaierror(socket.EAI_AGAIN, "resolver stalled")

    monkeypatch.setattr(verifier.socket, "getaddrinfo", blocked_dns)
    started = asyncio.get_running_loop().time()
    with pytest.raises(TimeoutError, match="public endpoint was not ready"):
        await verifier.wait_for_endpoint(
            "blocked.invalid",
            8000,
            timeout_seconds=0.03,
            poll_interval=0.005,
        )

    assert asyncio.get_running_loop().time() - started < 0.15


@pytest.mark.asyncio
async def test_endpoint_readiness_retries_refused_tcp_connection(monkeypatch) -> None:
    verifier = load_verifier()
    attempts = 0

    class Writer:
        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            pass

    async def open_connection(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionRefusedError("load balancer target not ready")
        return object(), Writer()

    monkeypatch.setattr(verifier.asyncio, "open_connection", open_connection)
    await verifier.wait_for_endpoint(
        "127.0.0.1",
        8000,
        timeout_seconds=1,
        poll_interval=0.01,
    )

    assert attempts == 2
