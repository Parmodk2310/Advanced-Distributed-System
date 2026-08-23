terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
  }
  backend "gcs" {
    bucket = "dist-sys-terraform-state"
    prefix = "gcp/production"
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

# VPC
resource "google_compute_network" "vpc" {
  name                    = "${var.project_name}-vpc"
  auto_create_subnetworks = false
  routing_mode            = "GLOBAL"
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${var.project_name}-subnet"
  ip_cidr_range = "10.0.0.0/16"
  region        = var.gcp_region
  network       = google_compute_network.vpc.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.1.0.0/16"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.2.0.0/16"
  }

  private_ip_google_access = true
}

# GKE Cluster
resource "google_container_cluster" "primary" {
  name     = "${var.project_name}-cluster"
  location = var.gcp_region

  network    = google_compute_network.vpc.name
  subnetwork = google_compute_subnetwork.subnet.name

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  release_channel {
    channel = "REGULAR"
  }

  node_pool {
    name       = "general"
    node_count = 3

    node_config {
      machine_type = "e2-medium"
      disk_size_gb = 50

      oauth_scopes = [
        "https://www.googleapis.com/auth/cloud-platform"
      ]

      labels = {
        role = "general"
      }

      tags = ["general"]
    }

    management {
      auto_repair  = true
      auto_upgrade = true
    }
  }

  node_pool {
    name       = "compute"
    node_count = 2

    node_config {
      machine_type = "c2-standard-4"
      disk_size_gb = 100

      oauth_scopes = [
        "https://www.googleapis.com/auth/cloud-platform"
      ]

      labels = {
        role = "compute"
      }

      taints {
        key    = "dedicated"
        value  = "compute"
        effect = "NO_SCHEDULE"
      }

      tags = ["compute"]
    }

    management {
      auto_repair  = true
      auto_upgrade = true
    }
  }

  depends_on = [google_compute_subnetwork.subnet]
}

# Cloud Load Balancer
resource "google_compute_global_address" "lb_ip" {
  name = "${var.project_name}-lb-ip"
}

resource "google_compute_managed_ssl_certificate" "main" {
  name = "${var.project_name}-ssl"

  managed {
    domains = [var.domain_name]
  }
}

# Cloud DNS
resource "google_dns_managed_zone" "main" {
  name        = "${var.project_name}-zone"
  dns_name    = "${var.domain_name}."
  description = "DNS zone for distributed system"
}

resource "google_dns_record_set" "app" {
  name         = google_dns_managed_zone.main.dns_name
  managed_zone = google_dns_managed_zone.main.name
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_global_address.lb_ip.address]
}

# Outputs
output "cluster_endpoint" {
  description = "GKE cluster endpoint"
  value       = google_container_cluster.primary.endpoint
}

output "cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.primary.name
}

output "load_balancer_ip" {
  description = "Load balancer IP"
  value       = google_compute_global_address.lb_ip.address
}