locals {
  name = "${var.project_name}-${var.environment}"
  tags = {
    Project     = var.project_name
    Environment = var.environment
    Owner       = var.owner
    ExpiresAt   = var.expires_at
    ManagedBy   = "terraform"
    Phase       = "7"
  }
}
