import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "deploy" / "terraform" / "aws"


def read(name):
    return (ROOT / name).read_text()


def test_cloud_foundation_is_inert_and_cost_bounded():
    variables = read("variables.tf")
    network = read("network.tf")
    assert 'variable "enable_eks"' in variables and "default = false" in variables
    assert "monthly_budget_usd" in variables and "<= 15" in variables
    assert 'cidr != "0.0.0.0/0"' in variables
    assert "aws_nat_gateway" not in network
    assert 'default = "1.36"' in variables


def test_remote_state_and_ebs_csi_are_present():
    assert 'backend "s3"' in read("versions.tf")
    eks = read("eks.tf")
    iam = read("iam.tf")
    assert re.search(
        r'addon_name\s*=\s*"aws-ebs-csi-driver"',
        eks,
    )
    assert "AmazonEBSCSIDriverPolicy" in iam


def test_temp_ecr_is_immutable_but_destroyable():
    t = read("ecr.tf")
    assert 'image_tag_mutability = "IMMUTABLE"' in t
    assert re.search(
        r"force_delete\s*=\s*true",
        t,
    )


def test_eks_uses_managed_default_envelope_encryption_for_clean_teardown():
    eks = read("eks.tf")
    assert 'resource "aws_kms_key"' not in eks
    assert "encryption_config" not in eks
