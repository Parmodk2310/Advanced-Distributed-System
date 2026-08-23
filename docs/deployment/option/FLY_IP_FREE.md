🚀 Fly.io Free Tier Deployment

## Why Fly.io?

**Free Tier includes:**
- **3 shared-cpu-1x VMs** (256MB RAM each) — FREE
- **3GB total volume storage** — FREE
- **160GB outbound data transfer** — FREE
- **Automatic global load balancing** — FREE
- **Built-in Prometheus metrics** — FREE
- **Custom domains + TLS** — FREE

**Best for:** Edge deployment, global distribution, simplicity.

---

## Architecture

```
┌─────────────────────────────────────────┐
│         Fly.io Edge Network             │
│    (Anycast load balancing globally)    │
│              ↓                          │
├─────────────────────────────────────────┤
│  Machine-0 (ord)                       │
│  ├── Node-0                            │
│  └── etcd-0 (volume)                   │
├─────────────────────────────────────────┤
│  Machine-1 (lax)                       │
│  ├── Node-1                            │
│  └── etcd-1 (volume)                   │
├─────────────────────────────────────────┤
│  Machine-2 (lhr)                       │
│  ├── Node-2                            │
│  └── etcd-2 + Prometheus (volume)      │
└─────────────────────────────────────────┘
```

---

## Step-by-Step Setup

### Step 1: Install Fly CLI

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh

# Windows
pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

### Step 2: Sign Up (No Credit Card Required)

```bash
fly auth signup
# Use GitHub account or email
# No credit card needed for free tier

fly auth login
```

### Step 3: Create App & Volumes

```bash
# Create app
cd distributed-system
fly apps create distributed-system

# Create volumes for etcd (one per region)
fly volumes create etcd_data --region ord --size 1 --app distributed-system
fly volumes create etcd_data --region lax --size 1 --app distributed-system
fly volumes create etcd_data --region lhr --size 1 --app distributed-system

# Verify volumes
fly volumes list --app distributed-system
```

### Step 4: Create fly.toml

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
  MAX_WORKERS = "1"
  MAX_QUEUE_DEPTH = "100"

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
  cpus = 1
  memory_mb = 256

[mounts]
  source = "etcd_data"
  destination = "/etcd-data"
```

### Step 5: Modify Dockerfile for Fly.io

Create `Dockerfile.fly`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install etcd (for embedded etcd in free tier)
RUN apt-get update && apt-get install -y etcd-server \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Start script that launches etcd + node
COPY scripts/fly-start.sh /app/fly-start.sh
RUN chmod +x /app/fly-start.sh

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000 9090 2379

CMD ["/app/fly-start.sh"]
```

Create `scripts/fly-start.sh`:

```bash
#!/bin/bash
set -e

# Start etcd in background (for free tier, each machine runs its own etcd)
# In production, use external etcd cluster
if [ ! -d "/etcd-data/member" ]; then
    etcd --data-dir /etcd-data \\
         --listen-client-urls http://0.0.0.0:2379 \\
         --advertise-client-urls http://localhost:2379 \\
         --listen-peer-urls http://0.0.0.0:2380 &
else
    etcd --data-dir /etcd-data \\
         --listen-client-urls http://0.0.0.0:2379 \\
         --advertise-client-urls http://localhost:2379 \\
         --listen-peer-urls http://0.0.0.0:2380 &
fi

sleep 2

# Start distributed node
exec python -m src --demo
```

### Step 6: Deploy

```bash
# Deploy to all regions
fly deploy --ha --dockerfile Dockerfile.fly

# Scale to 3 machines (one per region)
fly scale count 3 --region ord,lax,lhr

# Verify
fly status
# NAME    STATE   REGION  IMAGE
# app-1   started ord     distributed-system:latest
# app-2   started lax     distributed-system:latest
# app-3   started lhr     distributed-system:latest

# View logs
fly logs
```

### Step 7: Access Your App

```bash
# Get app URL
fly info
# Hostname: distributed-system.fly.dev

# Test API
curl https://distributed-system.fly.dev/health

# View metrics (built-in Prometheus)
fly metrics

# Or access Prometheus directly
fly proxy 9090:9090
# Open http://localhost:9090/metrics
```

### Step 8: Custom Domain (Free)

```bash
# Add custom domain
fly certs add dist-sys.yourdomain.com

# Add DNS CNAME record:
# dist-sys.yourdomain.com → distributed-system.fly.dev

# Verify
fly certs show
```

---

## Cost: $0

| Resource | Free Tier | Usage | Cost |
|----------|-----------|-------|------|
| 3x shared-cpu-1x | 3 VMs | 3 VMs | **$0** |
| Volume storage | 3GB | 3GB | **$0** |
| Data transfer | 160GB | ~50GB | **$0** |
| Custom domain + TLS | Unlimited | 1 | **$0** |
| **TOTAL** | | | **$0/month** |

---

## Limitations

- **256MB RAM per machine** (very tight for etcd + node + Prometheus)
- **No persistent etcd cluster** (each machine has isolated etcd)
- **No horizontal pod autoscaling** (manual `fly scale`)
- **Sleeping machines** (free machines may sleep after inactivity, auto-wake on request)

---

## Optimization for Free Tier

```bash
# Reduce memory usage
fly deploy --env MAX_WORKERS=1 --env MAX_QUEUE_DEPTH=50

# Use lighter base image
# In Dockerfile.fly: FROM python:3.12-alpine

# Disable Prometheus HTTP server (use fly metrics instead)
# Set METRICS_ENABLED=false in env

# Use SQLite instead of etcd (for state persistence)
# Modify src/storage/etcd_client.py to fallback to SQLite
```