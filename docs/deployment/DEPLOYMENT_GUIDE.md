# 🚀 Complete Deployment Guide

## Table of Contents
1. [Deployment Platforms Comparison](#deployment-platforms-comparison)
2. [Recommended Platform](#recommended-platform)
3. [Platform-Specific Deployment Guides](#platform-specific-deployment-guides)
4. [Security Hardening](#security-hardening)
5. [Monitoring & Alerting](#monitoring--alerting)
6. [Disaster Recovery](#disaster-recovery)
7. [Cost Optimization](#cost-optimization)

---

## Deployment Platforms Comparison

| Platform | Best For | Ease | Cost | Scalability | Managed K8s | Custom VMs |
|----------|----------|------|------|-------------|-------------|------------|
| **AWS EKS** | Enterprise, complex workloads | ⭐⭐ | $$$ | ⭐⭐⭐⭐⭐ | ✅ | ✅ |
| **Google GKE** | ML/AI, data-intensive | ⭐⭐ | $$$ | ⭐⭐⭐⭐⭐ | ✅ | ✅ |
| **Azure AKS** | Microsoft ecosystem | ⭐⭐ | $$$ | ⭐⭐⭐⭐⭐ | ✅ | ✅ |
| **DigitalOcean K8s** | Startups, simplicity | ⭐⭐⭐⭐ | $$ | ⭐⭐⭐⭐ | ✅ | ❌ |
| **Linode LKE** | Cost-conscious, simple | ⭐⭐⭐⭐ | $ | ⭐⭐⭐ | ✅ | ❌ |
| **Hetzner Cloud** | EU-focused, ultra-cheap | ⭐⭐⭐ | $ | ⭐⭐⭐ | ❌ | ✅ |
| **Fly.io** | Edge deployment, global | ⭐⭐⭐⭐⭐ | $$ | ⭐⭐⭐⭐ | ❌ | ✅ |
| **Railway** | Rapid prototyping | ⭐⭐⭐⭐⭐ | $$ | ⭐⭐⭐ | ❌ | ❌ |
| **Render** | Full-stack apps | ⭐⭐⭐⭐⭐ | $$ | ⭐⭐⭐ | ❌ | ❌ |
| **Vultr** | Budget bare metal | ⭐⭐⭐ | $ | ⭐⭐⭐ | ❌ | ✅ |

---

## Recommended Platform

### 🏆 Primary Recommendation: **AWS EKS + Fargate**

**Why AWS EKS is the best choice for this project:**

1. **Production-Grade Reliability**: 99.99% SLA, multi-AZ by default
2. **Auto-Scaling**: HPA + Cluster Autoscaler + Karpenter for cost-efficient scaling
3. **Managed etcd**: EKS manages the control plane (no etcd ops burden)
4. **Service Mesh Ready**: Easy integration with AWS App Mesh or Istio
5. **Security**: IAM integration, Secrets Manager, ACM for TLS certs
6. **Observability**: CloudWatch, X-Ray, Managed Prometheus/Grafana
7. **Cost at Scale**: Savings Plans + Spot Instances reduce costs by 60-70%

**Estimated Monthly Cost (3-node production):**
- EKS Control Plane: $72
- 3x t3.medium worker nodes (on-demand): $100
- ALB: $25
- NAT Gateway: $35
- Data transfer: $20
- **Total: ~$252/month** (can reduce to ~$120 with Spot instances)

### 🥈 Alternative: **Fly.io** (for simpler deployments)

**Why Fly.io is great for simpler use cases:**
- Global edge deployment (15+ regions)
- Built-in load balancing and auto-scaling
- Simple `fly deploy` workflow
- Built-in Prometheus metrics
- Volume support for etcd persistence
- **Cost: ~$50-100/month** for 3 nodes

### 🥉 Budget Alternative: **Hetzner Cloud + k3s**

**Why Hetzner for budget-conscious:**
- 3x CPX21 (4 vCPU, 8GB) = ~$30/month total
- k3s lightweight Kubernetes
- Full control over infrastructure
- EU data residency
- **Total: ~$35/month** including load balancer

---

## Platform-Specific Deployment Guides

### Option 1: AWS EKS (Recommended for Production)

#### Prerequisites
```bash
# Install tools
brew install awscli kubectl helm terraform

# Configure AWS
aws configure
aws eks update-kubeconfig --region us-east-1 --name distributed-system-cluster
```

#### Step 1: Provision Infrastructure with Terraform

```bash
cd terraform/aws

# Initialize
terraform init

# Plan
terraform plan -var="domain_name=dist-sys.yourdomain.com"

# Apply (takes ~15 minutes)
terraform apply

# Get outputs
terraform output cluster_endpoint
terraform output cluster_name
```

#### Step 2: Configure kubectl

```bash
aws eks update-kubeconfig \
  --region us-east-1 \
  --name $(terraform output -raw cluster_name)

kubectl get nodes
```

#### Step 3: Deploy with Helm

```bash
# Build and push Docker image
aws ecr get-login-password | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

docker build -t distributed-system:latest .
docker tag distributed-system:latest $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/distributed-system:latest
docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/distributed-system:latest

# Deploy
cd ../../helm/distributed-system

# Update values for AWS
helm upgrade --install dist-sys . \
  --namespace production --create-namespace \
  --set image.repository=$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/distributed-system \
  --set image.tag=latest \
  --set ingress.enabled=true \
  --set ingress.className=alb \
  --set ingress.annotations."alb\.ingress\.kubernetes\.io/scheme"=internet-facing \
  --set autoscaling.enabled=true \
  --set autoscaling.minReplicas=3 \
  --set autoscaling.maxReplicas=20 \
  --wait --timeout 10m

# Verify
kubectl get pods -n production
kubectl get svc -n production
kubectl get ingress -n production
```

#### Step 4: Configure DNS

```bash
# Get ALB DNS
ALB_DNS=$(kubectl get ingress dist-sys -n production -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Add Route53 record (or use your DNS provider)
aws route53 change-resource-record-sets \
  --hosted-zone-id YOUR_ZONE_ID \
  --change-batch file://dns-change.json
```

#### Step 5: Enable Monitoring

```bash
# Install AWS Managed Prometheus
aws amp create-workspace --alias distributed-system

# Install Grafana
helm repo add grafana https://grafana.github.io/helm-charts
helm install grafana grafana/grafana \
  --namespace monitoring --create-namespace \
  --set datasources.\"datasources.yaml\".datasources[0].url=$AMP_ENDPOINT

# Access Grafana
kubectl port-forward svc/grafana 3000:3000 -n monitoring
# Open http://localhost:3000 (admin/prom-operator)
```

---

### Option 2: Google GKE

#### Step 1: Provision with Terraform

```bash
cd terraform/gcp

export GCP_PROJECT_ID=your-project-id

terraform init
terraform plan -var="gcp_project_id=$GCP_PROJECT_ID"
terraform apply

# Get credentials
gcloud container clusters get-credentials $(terraform output -raw cluster_name) \
  --region us-central1
```

#### Step 2: Deploy

```bash
# Build and push to GCR
gcloud auth configure-docker
docker build -t gcr.io/$GCP_PROJECT_ID/distributed-system:latest .
docker push gcr.io/$GCP_PROJECT_ID/distributed-system:latest

# Deploy with Helm
helm upgrade --install dist-sys ./helm/distributed-system \
  --namespace production --create-namespace \
  --set image.repository=gcr.io/$GCP_PROJECT_ID/distributed-system \
  --set image.tag=latest \
  --set ingress.className=gce \
  --wait --timeout 10m
```

---

### Option 3: DigitalOcean Kubernetes (DOKS)

#### Step 1: Create Cluster

```bash
# Install doctl
brew install doctl
doctl auth init

# Create cluster
doctl kubernetes cluster create dist-sys-cluster \
  --region nyc1 \
  --version 1.29 \
  --node-pool "name=general;size=s-2vcpu-4gb;count=3;auto-scale=true;min-nodes=3;max-nodes=10" \
  --node-pool "name=compute;size=c-4;count=2;auto-scale=true;min-nodes=2;max-nodes=6"

# Save kubeconfig
doctl kubernetes cluster kubeconfig save dist-sys-cluster
```

#### Step 2: Deploy

```bash
# Build and push to DOCR
doctl registry login
docker build -t registry.digitalocean.com/your-registry/distributed-system:latest .
docker push registry.digitalocean.com/your-registry/distributed-system:latest

# Deploy
helm upgrade --install dist-sys ./helm/distributed-system \
  --namespace production --create-namespace \
  --set image.repository=registry.digitalocean.com/your-registry/distributed-system \
  --set ingress.className=nginx \
  --set etcd.enabled=true \
  --wait --timeout 10m

# Expose via Load Balancer
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: dist-sys-lb
  namespace: production
  annotations:
    service.beta.kubernetes.io/do-loadbalancer-protocol: "https"
    service.beta.kubernetes.io/do-loadbalancer-certificate-id: "your-cert-id"
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: distributed-system
  ports:
    - port: 443
      targetPort: 8000
EOF
```

**Cost: ~$72/month** (3x s-2vcpu-4gb at $24/month each)

---

### Option 4: Fly.io (Simplest)

#### Step 1: Install Fly CLI

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
```

#### Step 2: Create App

```bash
# Create app
fly apps create distributed-system

# Create volumes for etcd (one per region)
fly volumes create etcd_data --region ord --size 10
fly volumes create etcd_data --region lax --size 10
fly volumes create etcd_data --region lhr --size 10
```

#### Step 3: Deploy with fly.toml

```toml
# fly.toml
app = "distributed-system"
primary_region = "ord"

[build]
  dockerfile = "Dockerfile"

[env]
  NODE_HOST = "0.0.0.0"
  NODE_PORT = "8000"
  USE_TLS = "false"
  ETCD_ENDPOINTS = "http://localhost:2379"
  METRICS_PORT = "9090"

[[services]]
  internal_port = 8000
  protocol = "tcp"
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 3

  [[services.ports]]
    handlers = ["http"]
    port = 80

  [[services.ports]]
    handlers = ["tls", "http"]
    port = 443

[[services]]
  internal_port = 9090
  protocol = "tcp"

  [[services.ports]]
    port = 9090

[[vm]]
  cpu_kind = "shared"
  cpus = 2
  memory_mb = 512
```

```bash
# Deploy
fly deploy --ha

# Scale
fly scale count 3 --region ord,lax,lhr

# Check status
fly status
fly logs
```

**Cost: ~$15/month per node** (shared-cpu-2x, 512MB) = ~$45/month total

---

### Option 5: Hetzner Cloud + k3s (Budget)

#### Step 1: Provision VMs

```bash
# Install hcloud CLI
brew install hcloud
hcloud context create my-project

# Create servers
for i in 0 1 2; do
  hcloud server create \
    --name dist-node-$i \
    --type cpx21 \
    --image ubuntu-22.04 \
    --location nbg1 \
    --ssh-key your-key
    
  hcloud server add-label dist-node-$i role=general
done

# Create load balancer
hcloud load-balancer create \
  --name dist-sys-lb \
  --type lb11 \
  --location nbg1
```

#### Step 2: Install k3s

```bash
# On node-0 (master)
ssh root@dist-node-0 \
  "curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC='server --cluster-init --tls-san dist-node-0' sh -"

# Get token
TOKEN=$(ssh root@dist-node-0 "cat /var/lib/rancher/k3s/server/node-token")

# On node-1, node-2 (workers)
for i in 1 2; do
  ssh root@dist-node-$i \
    "curl -sfL https://get.k3s.io | K3S_URL=https://dist-node-0:6443 K3S_TOKEN=$TOKEN sh -"
done

# Copy kubeconfig
scp root@dist-node-0:/etc/rancher/k3s/k3s.yaml ~/.kube/config
sed -i 's/127.0.0.1/dist-node-0/' ~/.kube/config
```

#### Step 3: Deploy

```bash
# Deploy with kubectl directly
kubectl apply -f k8s/base/

# Or use Helm
helm upgrade --install dist-sys ./helm/distributed-system \
  --set etcd.enabled=false \
  --set persistence.enabled=true
```

**Cost: ~$30/month** (3x CPX21 at ~$10/month each)

---

## Security Hardening

### Pre-Deployment Checklist

- [ ] **TLS**: Enable mTLS with valid certificates (not self-signed in prod)
- [ ] **Network Policies**: Restrict pod-to-pod communication
- [ ] **RBAC**: Least-privilege Kubernetes RBAC
- [ ] **Secrets**: Use external secrets (AWS Secrets Manager / GCP Secret Manager)
- [ ] **Pod Security**: Run as non-root, read-only root filesystem
- [ ] **Image Scanning**: Trivy/Grype scan before deployment
- [ ] **WAF**: Enable AWS WAF / Cloudflare for edge protection
- [ ] **DDoS**: Enable AWS Shield Standard / Cloudflare

### Kubernetes Network Policy

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: dist-sys-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: distributed-system
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8000
    - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: distributed-system
      ports:
        - protocol: TCP
          port: 8000
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: etcd
      ports:
        - protocol: TCP
          port: 2379
```

---

## Monitoring & Alerting

### Prometheus Alerting Rules

```yaml
groups:
  - name: distributed-system
    rules:
      - alert: HighErrorRate
        expr: rate(distsys_requests_failed_total[5m]) / rate(distsys_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate on {{ $labels.node_id }}"
          
      - alert: CircuitBreakerOpen
        expr: distsys_circuit_state == 2  # OPEN state
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Circuit breaker OPEN on {{ $labels.node_id }}"
          
      - alert: HighLatency
        expr: distsys_latency_p95 > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P95 latency > 100ms on {{ $labels.node_id }}"
          
      - alert: NodeDown
        expr: distsys_cluster_members < 3
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Cluster has fewer than 3 nodes"
```

### Grafana Dashboard

Import dashboard ID `1860` (Node Exporter) and create custom panels:
- Request rate (req/s)
- Error rate (%)
- Latency heatmap
- Circuit breaker state
- Backpressure load
- Worker pool utilization
- Cluster topology

---

## Disaster Recovery

### Backup Strategy

```bash
# etcd backup (run as CronJob)
etcdctl snapshot save /backup/etcd-$(date +%Y%m%d-%H%M%S).db

# CRDT state backup
kubectl exec -it dist-node-0 -- python -c "
import json
from src.storage.etcd_client import EtcdStateStore
store = EtcdStateStore()
import asyncio
asyncio.run(store.connect())
# Dump all CRDTs
"

# Automated backup to S3
aws s3 sync /backup/ s3://dist-sys-backups/etcd/ --delete
```

### Recovery Procedures

**Scenario 1: Single node failure**
```bash
# Automatic: StatefulSet recreates pod
# Manual: Verify new pod joins gossip cluster
kubectl logs dist-node-2 -f
```

**Scenario 2: etcd data loss**
```bash
# Restore from snapshot
etcdctl snapshot restore etcd-backup.db \
  --data-dir=/var/lib/etcd-new \
  --name etcd-0

# Restart etcd pods
kubectl rollout restart statefulset/etcd
```

**Scenario 3: Complete cluster loss**
```bash
# 1. Restore infrastructure from Terraform
terraform apply

# 2. Restore etcd from backup
# 3. Redeploy application
helm upgrade --install dist-sys ./helm/distributed-system

# 4. Verify CRDT consistency
kubectl exec -it dist-node-0 -- python scripts/verify-crdt.py
```

---

## Cost Optimization

### AWS Cost Reduction Strategies

| Strategy | Savings | Implementation |
|----------|---------|----------------|
| Spot Instances | 60-70% | Use Karpenter + Spot node pool |
| Savings Plans | 20-30% | 1-year compute commitment |
| Graviton (ARM) | 20% | Use t4g/c6g instance types |
| Reserved Capacity | 40% | For predictable baseline load |
| Right-sizing | 15-25% | Monitor actual CPU/memory usage |

### Example: Optimized AWS Setup

```bash
# Use Graviton + Spot
helm upgrade --install dist-sys ./helm/distributed-system \
  --set nodeSelector."beta\.kubernetes\.io/arch"=arm64 \
  --set tolerations[0].key=spot \
  --set tolerations[0].operator=Exists \
  --set tolerations[0].effect=NoSchedule

# Karpenter for intelligent scaling
helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter \
  --namespace karpenter --create-namespace
```

**Optimized cost: ~$120/month** (vs $252 baseline)

---

## Quick Start Commands

```bash
# Local development
make install && make certs && make cluster

# Docker Compose
make docker-up

# Kubernetes (any provider)
kubectl apply -k k8s/base/

# Helm (any provider)
helm upgrade --install dist-sys ./helm/distributed-system --namespace production --create-namespace

# Terraform (AWS)
cd terraform/aws && terraform apply

# Fly.io
fly deploy

# Benchmark
python benchmark/benchmark.py --nodes 3

# Health check
python scripts/health-check.py --nodes 3
```
