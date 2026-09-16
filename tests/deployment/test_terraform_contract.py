from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TF = ROOT / "deploy/terraform/aws"


def all_tf() -> str:
    return "\n".join(path.read_text() for path in sorted(TF.glob("*.tf")))


def test_terraform_is_disabled_and_cost_bounded_by_default() -> None:
    text = all_tf()
    variables = (TF / "variables.tf").read_text()
    assert 'variable "enable_eks"' in variables
    assert "default = false" in variables
    assert 'default = "ap-south-1"' in text
    assert "var.monthly_budget_usd <= 15" in text
    assert 'default = ["t3.medium"]' in text
    assert "default = 1" in text and "default = 2" in text


def test_network_and_cluster_contract() -> None:
    text = all_tf()
    compact = " ".join(text.split())
    assert 'resource "aws_subnet" "public"' in text
    assert "count = var.enable_eks ? 2 : 0" in compact
    assert "aws_nat_gateway" not in text
    assert 'cidr != "0.0.0.0/0"' in compact
    assert "endpoint_private_access = true" in compact
    assert 'capacity_type = "ON_DEMAND"' in compact
    assert "encryption_config" in text


def test_terraform_does_not_own_application_resources() -> None:
    text = all_tf()
    assert "helm_release" not in text
    assert 'resource "kubernetes_' not in text
    assert 'image_tag_mutability = "IMMUTABLE"' in text
    assert "scan_on_push = true" in text
