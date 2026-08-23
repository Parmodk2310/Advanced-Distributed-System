# 🖥️ Self-Hosted / Raspberry Pi Deployment (TRULY FREE)

## Why Self-Hosted?

**Cost:** $0 (use existing hardware)
**Control:** Full control over infrastructure
**Privacy:** Data never leaves your network
**Learning:** Best way to understand distributed systems

---

## Option A: Raspberry Pi Cluster (3x Pi 4/5)

### Hardware

| Component | Cost (one-time) | Specs |
|-----------|----------------|-------|
| 3x Raspberry Pi 5 | $210 ($70 each) | 4-core ARM, 8GB RAM |
| 3x MicroSD 64GB | $30 ($10 each) | Class 10 |
| 1x Network Switch | $15 | 5-port Gigabit |
| 3x Ethernet Cables | $10 | Cat6 |
| 1x USB-C Power Hub | $25 | 5-port 60W |
| **Total** | **~$290** | |

### Setup

```bash
# Flash Ubuntu Server 22.04 LTS to all 3 SD cards
# Using Raspberry Pi Imager: https://www.raspberrypi.com/software/

# Boot all 3 Pis
# Find IPs on your network
nmap -sn 192.168.1.0/24 | grep "raspberry"

# SSH into each
ssh ubuntu@192.168.1.101  # pi-0
ssh ubuntu@192.168.1.102  # pi-1
ssh ubuntu@192.168.1.103  # pi-2

# On all 3: Install dependencies
sudo apt update && sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER
newgrp docker

# On pi-0: Create docker-compose.yml
cat > docker-compose.yml <<'EOF'
version: "3.8"

services:
  etcd:
    image: quay.io/coreos/etcd:v3.5.11
    environment:
      - ETCD_NAME=etcd0
      - ETCD_DATA_DIR=/etcd-data
      - ETCD_LISTEN_CLIENT_URLS=http://0.0.0.0:2379
      - ETCD_ADVERTISE_CLIENT_URLS=http://etcd:2379
      - ETCD_LISTEN_PEER_URLS=http://0.0.0.0:2380
      - ETCD_INITIAL_ADVERTISE_PEER_URLS=http://etcd:2380
      - ETCD_INITIAL_CLUSTER=etcd0=http://etcd:2380
      - ETCD_INITIAL_CLUSTER_TOKEN=dist-sys-cluster
      - ETCD_INITIAL_CLUSTER_STATE=new
    volumes:
      - etcd-data:/etcd-data
    networks:
      - dist-sys

  node-0:
    build: .
    environment:
      - NODE_ID=node-0
      - NODE_HOST=0.0.0.0
      - NODE_PORT=8000
      - PEERS=pi-1:8000,pi-2:8000
      - ETCD_ENDPOINTS=http://etcd:2379
      - USE_TLS=false
      - MAX_WORKERS=2
    ports:
      - "8000:8000"
      - "9090:9090"
    networks:
      - dist-sys
    depends_on:
      - etcd

volumes:
  etcd-data:

networks:
  dist-sys:
    driver: bridge
EOF

# Build and run
docker-compose up --build -d

# On pi-1 and pi-2: Similar setup with different NODE_ID and PEERS
```

### Performance

| Metric | Raspberry Pi 5 (8GB) |
|--------|---------------------|
| Echo throughput | ~2,000 req/s |
| Hash throughput | ~500 req/s |
| Power consumption | ~15W total (3 nodes) |
| Annual power cost | ~$15 (@ $0.12/kWh) |

---

## Option B: Old Laptop / Desktop

```bash
# Any x86_64 machine with 8GB+ RAM
# Install Ubuntu Server or Proxmox VE

# Proxmox: Create 3 VMs
# VM-1: 2 vCPU, 2GB RAM (Node-0 + etcd-0)
# VM-2: 2 vCPU, 2GB RAM (Node-1 + etcd-1)
# VM-3: 2 vCPU, 2GB RAM (Node-2 + etcd-2 + Prometheus)

# Use the docker-compose.yml from above
```

---

## Option C: Free Cloud VPS (Credit-Based)

| Provider | Free Credit | Duration | Best For |
|----------|-------------|----------|----------|
| **Google Cloud** | $300 | 90 days | Experimentation |
| **AWS** | Free tier | 12 months | 750 hrs t2.micro |
| **Azure** | $200 | 30 days | Testing |
| **DigitalOcean** | $200 | 60 days | Simple VMs |
| **Vultr** | $250 | 30 days | Bare metal |
| **Linode** | $100 | 60 days | Reliable VMs |

**Strategy:** Use $300 Google Cloud credit to run 3x e2-medium VMs for ~3 months free.

```bash
# Google Cloud Free Tier Deployment
gcloud auth login
gcloud config set project YOUR_PROJECT

# Create 3 VMs (within $300 credit)
for i in 0 1 2; do
  gcloud compute instances create dist-node-$i \\
    --zone=us-central1-a \\
    --machine-type=e2-medium \\
    --image-family=ubuntu-2204-lts \\
    --image-project=ubuntu-os-cloud \\
    --boot-disk-size=50GB \\
    --tags=http-server,https-server
done

# Deploy with docker-compose (same as self-hosted)
```

---

## Cost Comparison: All Free Options

| Platform | Monthly Cost | Setup Complexity | Reliability | Best For |
|----------|-------------|------------------|-------------|----------|
| **Oracle Cloud** | **$0** ⭐ | Medium | High | Production-like free hosting |
| **Fly.io** | **$0** ⭐ | Low | Medium | Global edge, simplicity |
| **Render** | **$0** ⭐ | Very Low | Medium | Rapid prototyping |
| **Railway** | **$0** ⭐ | Very Low | Medium | Git-based workflows |
| **Raspberry Pi** | **$1** (power) | High | Low | Learning, IoT, home lab |
| **Google Cloud** | **$0** (credits) | Medium | High | 3-month experimentation |
| **AWS Free Tier** | **$0** (12mo) | High | High | Learning AWS |

---

## My Recommendation

| Use Case | Recommended Platform | Why |
|----------|---------------------|-----|
| **Learning / Home Lab** | Raspberry Pi + k3s | Hands-on, $0 ongoing |
| **Production-like free hosting** | Oracle Cloud Free Tier | Most resources, always free |
| **Global edge deployment** | Fly.io | Simplest, built-in CDN |
| **Rapid prototyping** | Render | Git-based, instant deploys |
| **3-month intensive project** | Google Cloud ($300 credit) | Full GCP features |
| **Resume portfolio project** | Fly.io or Render | Custom domain, always online |