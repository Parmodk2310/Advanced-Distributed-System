# Phase 7 AWS Terraform

This module is inert until it is applied. `enable_eks=false` is the default. The Phase 7B workflow uses `enable_eks=true` only after an explicit approval gate.

A pre-existing S3 backend and DynamoDB lock table are required for cross-run plan/apply/destroy safety. Copy `backend.hcl.example` to a local untracked file or generate it from protected GitHub variables. Never commit backend credentials or state.

The temporary EKS profile deliberately uses public worker subnets and no NAT Gateway to bound demo complexity/cost. It is not the recommended permanent production topology.
