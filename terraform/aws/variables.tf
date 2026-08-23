variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "distributed-system"
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "dist-sys.example.com"
}

variable "common_tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "distributed-system"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}