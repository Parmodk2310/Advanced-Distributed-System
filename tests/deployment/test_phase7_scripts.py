import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "phase7"


def read(p):
    return (ROOT / p).read_text()


def test_shell_scripts_use_strict_mode_and_parse():
    scripts = sorted(SCRIPTS.glob("*.sh"))
    assert scripts
    for script in scripts:
        text = script.read_text()
        assert text.startswith("#!/usr/bin/env bash\nset -euo pipefail\n")
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_kind_topology_is_one_control_plane_two_workers():
    cfg = yaml.safe_load(read("deploy/kind/cluster.yaml"))
    assert cfg["nodes"] == [{"role": "control-plane"}, {"role": "worker"}, {"role": "worker"}]


def test_local_etcd_is_single_lightweight_dev_instance():
    text = read("deploy/kind/etcd.yaml")
    assert "replicas: 1" in text
    assert "emptyDir:" in text
    assert "quay.io/coreos/etcd:v3.5.15@sha256:" in text
    assert "runAsNonRoot: true" in text


def test_tls_is_ephemeral_and_has_public_demo_sni_name():
    text = read("scripts/phase7/generate_tls_secret.sh")
    assert 'chmod 600 "$TLS_DIR/ca/ca.key"' in text
    assert "--dry-run=client -o yaml | kubectl apply -f -" in text
    assert "DNS:phase7-public" in text
    assert "> secret.yaml" not in text


def test_aws_teardown_allows_only_exact_backend_resources_and_waits_for_ebs():
    text = read("scripts/phase7/verify_aws_teardown.sh")

    assert "PHASE7_TEARDOWN_TIMEOUT_SECONDS:-600" in text
    assert "PHASE7_TF_STATE_BUCKET" in text
    assert "PHASE7_TF_LOCK_TABLE" in text
    assert "arn:aws:s3:::${state_bucket}" in text
    assert "arn:aws:dynamodb:${region}:${account_id}:table/${lock_table}" in text
    assert "unexpected_tagged_resources" in text


def _write_fake_aws_for_teardown(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_aws = fake_bin / "aws"
    fake_aws.write_text("""#!/usr/bin/env bash
set -euo pipefail

if [[ "$1 $2" == "sts get-caller-identity" ]]; then
  printf '%s\n' '212173345339'
  exit 0
fi

if [[ "$1 $2" == "resourcegroupstaggingapi get-resources" ]]; then
  printf '%s\n' '[
    "arn:aws:s3:::phase7-state",
    "arn:aws:dynamodb:ap-south-1:212173345339:table/phase7-lock",
    "arn:aws:ec2:ap-south-1:212173345339:volume/vol-0123456789abcdef0"
  ]'
  exit 0
fi

if [[ "$1 $2" == "ec2 describe-volumes" ]]; then
  if [[ "${FAKE_VOLUME_EXISTS:-false}" == "true" ]]; then
    printf '%s\n' '[{"VolumeId":"vol-0123456789abcdef0"}]'
    exit 0
  fi

  echo "An error occurred (InvalidVolume.NotFound)" >&2
  exit 254
fi

echo "unexpected fake AWS invocation: $*" >&2
exit 99
""")
    fake_aws.chmod(0o755)
    return fake_bin


def _run_teardown_with_fake_aws(
    tmp_path: Path,
    *,
    volume_exists: bool,
) -> subprocess.CompletedProcess[str]:
    fake_bin = _write_fake_aws_for_teardown(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "AWS_REGION": "ap-south-1",
            "PHASE7_TF_STATE_BUCKET": "phase7-state",
            "PHASE7_TF_LOCK_TABLE": "phase7-lock",
            "PHASE7_TEARDOWN_TIMEOUT_SECONDS": "1",
            "PHASE7_TEARDOWN_POLL_SECONDS": "1",
            "FAKE_VOLUME_EXISTS": str(volume_exists).lower(),
        }
    )

    return subprocess.run(
        ["bash", str(SCRIPTS / "verify_aws_teardown.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )


def test_aws_teardown_ignores_confirmed_deleted_ebs_tagging_records(
    tmp_path: Path,
) -> None:
    result = _run_teardown_with_fake_aws(
        tmp_path,
        volume_exists=False,
    )

    assert result.returncode == 0, result.stderr
    assert '"aws_teardown":"pass"' in result.stdout
    assert '"unexpected_tagged_resources":0' in result.stdout


def test_aws_teardown_rejects_ebs_volume_that_still_exists(
    tmp_path: Path,
) -> None:
    result = _run_teardown_with_fake_aws(
        tmp_path,
        volume_exists=True,
    )

    assert result.returncode == 1
    assert "vol-0123456789abcdef0" in result.stderr


def test_public_endpoint_verifier_waits_for_dns_and_tcp_readiness() -> None:
    verifier = read("scripts/phase7/verify_public_endpoint.py")

    assert "--readiness-timeout" in verifier
    assert "--poll-interval" in verifier
    assert "socket.getaddrinfo" in verifier
    assert "asyncio.open_connection" in verifier
    assert "waiting for public endpoint readiness" in verifier
    assert "public endpoint was not ready" in verifier


def test_lifecycle_scripts_never_directly_delete_ebs_volumes() -> None:
    scripts = "\n".join(
        path.read_text() for path in sorted(path for path in SCRIPTS.glob("*") if path.is_file())
    )

    assert "aws ec2 delete-volume" not in scripts


def test_ebs_wait_has_timeout_diagnostics() -> None:
    wait_script = read("scripts/phase7/wait_for_ebs_deletion.sh")

    assert "PHASE7_EBS_WAIT_TIMEOUT_SECONDS" in wait_script
    assert "PHASE7_EBS_WAIT_POLL_SECONDS" in wait_script
    assert "timed out waiting for Phase 7 EBS volumes" in wait_script
    assert "aws ec2 describe-volumes" in wait_script
    assert "aws ec2 delete-volume" not in wait_script
