resource "aws_eks_cluster" "this" {
  count    = var.enable_eks ? 1 : 0
  name     = local.name
  role_arn = aws_iam_role.eks[0].arn
  version  = var.kubernetes_version
  access_config {
    authentication_mode                         = "API_AND_CONFIG_MAP"
    bootstrap_cluster_creator_admin_permissions = true
  }
  vpc_config {
    subnet_ids              = aws_subnet.public[*].id
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.kubernetes_api_cidrs
  }
  depends_on = [aws_iam_role_policy_attachment.eks]
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
  update_config { max_unavailable = 1 }
  depends_on = [
    aws_iam_role_policy_attachment.worker,
    aws_iam_role_policy_attachment.cni,
    aws_iam_role_policy_attachment.ecr
  ]
}
resource "aws_eks_addon" "ebs_csi" {
  count                       = var.enable_eks ? 1 : 0
  cluster_name                = aws_eks_cluster.this[0].name
  addon_name                  = "aws-ebs-csi-driver"
  service_account_role_arn    = aws_iam_role.ebs_csi[0].arn
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "PRESERVE"
  depends_on                  = [aws_eks_node_group.this, aws_iam_role_policy_attachment.ebs_csi]
}
