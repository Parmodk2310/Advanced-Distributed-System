# Phase 7 AWS infrastructure

This module is safe by default: `enable_eks=false` creates the ECR repository and budget only. It never deploys Helm resources. The demonstration profile uses two public subnets, no NAT Gateway, and one on-demand `t3.medium` worker (`1/1/2` min/desired/max). This reduces cost but is not a production private-node topology.

Copy `terraform.tfvars.example`, replace all placeholders, restrict the API CIDR to your current public `/32`, then run `terraform init -backend=false`, `terraform validate`, and `terraform plan`. Do not apply until the exact plan and estimated cost receive separate approval.
