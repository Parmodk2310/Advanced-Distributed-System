resource "aws_eks_cluster" "this" {
  count    = var.enable_eks ? 1 : 0
  name     = local.name
  role_arn = aws_iam_role.eks[0].arn
  version  = "1.32"

  vpc_config {
    subnet_ids              = aws_subnet.public[*].id
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.kubernetes_api_cidrs
  }

  encryption_config {
    provider {
      key_arn = aws_kms_key.eks[0].arn
    }
    resources = ["secrets"]
  }

  depends_on = [aws_iam_role_policy_attachment.eks]
}

resource "aws_kms_key" "eks" {
  count                   = var.enable_eks ? 1 : 0
  description             = "Phase 7 temporary EKS secrets"
  enable_key_rotation     = true
  deletion_window_in_days = 7
}

resource "aws_eks_node_group" "this" {
  count           = var.enable_eks ? 1 : 0
  cluster_name    = aws_eks_cluster.this[0].name
  node_group_name = "demo"
  node_role_arn   = aws_iam_role.node[0].arn
  subnet_ids      = aws_subnet.public[*].id
  capacity_type   = "ON_DEMAND"
  instance_types  = var.node_instance_types
  disk_size       = 20

  scaling_config {
    min_size     = var.node_min_size
    desired_size = var.node_desired_size
    max_size     = var.node_max_size
  }

  update_config {
    max_unavailable = 1
  }

  depends_on = [aws_iam_role_policy_attachment.worker, aws_iam_role_policy_attachment.cni, aws_iam_role_policy_attachment.ecr]
}
