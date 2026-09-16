output "ecr_repository_url" {
  value = aws_ecr_repository.node.repository_url
}

output "cluster_name" {
  value = try(aws_eks_cluster.this[0].name, null)
}

output "region" {
  value = var.aws_region
}
