variable "aws_region" {
  type    = string
  default = "ap-south-1"

  validation {
    condition     = var.aws_region == "ap-south-1"
    error_message = "Phase 7 is designed for ap-south-1."
  }
}

variable "project_name" {
  type    = string
  default = "advanced-distributed-system"
}

variable "environment" {
  type    = string
  default = "phase7-demo"
}

variable "owner" {
  type        = string
  description = "Mandatory owner tag."
}

variable "expires_at" {
  type        = string
  description = "Mandatory ISO-8601 expiry tag."
}

variable "budget_email" {
  type        = string
  sensitive   = true
  description = "Budget alert recipient."
}

variable "monthly_budget_usd" {
  type    = number
  default = 15

  validation {
    condition     = var.monthly_budget_usd > 0 && var.monthly_budget_usd <= 15
    error_message = "Budget ceiling must be greater than 0 and no more than 15 USD."
  }
}

variable "enable_eks" {
  type    = bool
  default = false
}

variable "kubernetes_version" {
  type    = string
  default = "1.36"

  validation {
    condition     = contains(["1.34", "1.35", "1.36"], var.kubernetes_version)
    error_message = "Use an EKS Kubernetes version in standard support for this bundle."
  }
}

variable "kubernetes_api_cidrs" {
  type    = list(string)
  default = ["192.0.2.1/32"]

  validation {
    condition     = length(var.kubernetes_api_cidrs) > 0 && alltrue([for cidr in var.kubernetes_api_cidrs : cidr != "0.0.0.0/0"])
    error_message = "Restrict the EKS public API to explicit CIDRs; 0.0.0.0/0 is forbidden."
  }
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.medium"]
}

variable "node_min_size" {
  type    = number
  default = 1
}

variable "node_desired_size" {
  type    = number
  default = 1
}

variable "node_max_size" {
  type    = number
  default = 2
}
