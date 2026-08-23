variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "distributed-system"
}

variable "domain_name" {
  description = "Domain name"
  type        = string
  default     = "dist-sys.example.com"
}