# 🏆 Oracle Cloud Free Tier Deployment (BEST FREE OPTION)

## Why Oracle Cloud?

**Always Free Tier includes:**
- **2x AMD-based Compute VMs** (1/8 OCPU, 1GB RAM each) — FOREVER FREE
- **4x ARM-based Compute VMs** (up to 3,000 OCPU hours, 18,000 GB hours) — FOREVER FREE
- **200GB block storage** — FOREVER FREE
- **10TB outbound data transfer** — FOREVER FREE
- **2x Load Balancers** — FOREVER FREE

**Total free capacity:** Equivalent to ~$200/month in AWS.

---

## Architecture for Free Tier

```
┌─────────────────────────────────────────┐
│  Oracle Cloud Load Balancer (Free)      │
│         ↓                               │
├─────────────────────────────────────────┤
│  VM-1 (ARM, 2 OCPU, 6GB)              │
│  ├── Node-0 (distributed system)       │
│  └── etcd-0                            │
├─────────────────────────────────────────┤
│  VM-2 (ARM, 2 OCPU, 6GB)              │
│  ├── Node-1 (distributed system)       │
│  └── etcd-1                            │
├─────────────────────────────────────────┤
│  VM-3 (ARM, 2 OCPU, 6GB)              │
│  ├── Node-2 (distributed system)       │
│  ├── etcd-2                            │
│  └── Prometheus + Grafana              │
└─────────────────────────────────────────┘
```

---

## Step-by-Step Setup

### Step 1: Create Oracle Cloud Account

1. Go to [cloud.oracle.com](https://cloud.oracle.com)
2. Sign up with email (credit card required for verification, **NOT charged**)
3. Select home region (choose closest: `us-ashburn-1`, `eu-frankfurt-1`, etc.)

### Step 2: Create ARM VMs (Ampere A1)

```bash
# Using OCI CLI (install: brew install oci-cli)
oci setup config

# Create 3 VMs with 2 OCPUs and 6GB RAM each
for i in 0 1 2; do
  oci compute instance launch \\
    --availability-domain $(oci iam availability-domain list --query 'data[0].name' --raw-output) \\
    --display-name dist-node-$i \\
    --shape VM.Standard.A1.Flex \\
    --shape-config '{"ocpus": 2, "memoryInGBs": 6}' \\
    --image-id $(oci compute image list --operating-system "Oracle Linux" --operating-system-version "8" --shape "VM.Standard.A1.Flex" --query 'data[0].id' --raw-output) \\
    --subnet-id YOUR_SUBNET_ID \\
    --ssh-authorized-keys-file ~/.ssh/id_rsa.pub \\
    --boot-volume-size-in-gbs 50
done
```

**Or via Console:**
1. Compute → Instances → Create Instance
2. Shape: `VM.Standard.A1.Flex`
3. OCPUs: 2, Memory: 6GB
4. Image: Oracle Linux 8 or Ubuntu 22.04
5. Boot volume: 50GB
6. Add SSH key
7. Repeat 3 times

### Step 3: Configure Network

```bash
# Get public IPs
for i in 0 1 2; do
  oci compute instance list --query "data[?\\"display-name\\"=='dist-node-$i'].\\"public-ip\\""
done

# Open ports in Security List
oci network security-list update \\
  --security-list-id YOUR_SL_ID \\
  --ingress-security-rules '[
    {"protocol": "6", "source": "0.0.0.0/0", "tcpOptions": {"destinationPortRange": {"min": 22, "max": 22}}},
    {"protocol": "6", "source": "0.0.0.0/0", "tcpOptions": {"destinationPortRange": {"min": 8000, "max": 8002}}},
    {"protocol": "6", "source": "0.0.0.0/0", "tcpOptions": {"destinationPortRange": {"min": 9090, "max": 9093}}},
    {"protocol": "6", "source": "0.0.0.0/0", "tcpOptions": {"destinationPortRange": {"min": 2379, "max": 2380}}},
    {"protocol": "17", "source": "0.0.0.0/0", "udpOptions": {"destinationPortRange": {"min": 8000, "max": 8002}}}
  ]'
```

### Step 4: Install Docker & k3s on Each VM

```bash
# SSH into each VM
ssh opc@VM_PUBLIC_IP

# Install Docker
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
newgrp docker

# Install k3s (lightweight Kubernetes)
# On VM-0 (master)
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --cluster-init --tls-san $(curl -s ifconfig.me)" sh -

# Get token
sudo cat /var/lib/rancher/k3s/server/node-token
# Save: K3S_TOKEN=K10xxxxxxxx::server:xxxxxxxx

# On VM-1 and VM-2 (workers)
curl -sfL https://get.k3s.io | K3S_URL=https://VM-0-PRIVATE-IP:6443 K3S_TOKEN=YOUR_TOKEN sh -
```

### Step 5: Deploy from Local Machine

```bash
# Copy kubeconfig
scp opc@VM-0-PUBLIC-IP:/etc/rancher/k3s/k3s.yaml ~/.kube/oracle-config
sed -i 's/127.0.0.1/VM-0-PUBLIC-IP/' ~/.kube/oracle-config
export KUBECONFIG=~/.kube/oracle-config

# Verify
kubectl get nodes
# NAME          STATUS   ROLES                       AGE
# dist-node-0   Ready    control-plane,etcd,master   2m
# dist-node-1   Ready    <none>                     1m
# dist-node-2   Ready    <none>                     1m

# Label nodes for scheduling
kubectl label node dist-node-0 node-role=general
kubectl label node dist-node-1 node-role=general
kubectl label node dist-node-2 node-role=monitoring

# Deploy
cd distributed-system
kubectl apply -k k8s/base/

# Or with Helm
helm upgrade --install dist-sys ./helm/distributed-system \\
  --namespace production --create-namespace \\
  --set etcd.enabled=false \\
  --set persistence.enabled=true

# Check status
kubectl get pods -n production -o wide
kubectl logs -l app.kubernetes.io/name=distributed-system -n production -f
```

### Step 6: Expose via Load Balancer

```bash
# Create free load balancer
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: dist-sys-lb
  namespace: production
  annotations:
    oci.oraclecloud.com/load-balancer-type: "lb"
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: distributed-system
  ports:
    - name: grpc
      port: 80
      targetPort: 8000
    - name: metrics
      port: 9090
      targetPort: 9090
EOF

# Get LB IP
kubectl get svc dist-sys-lb -n production
# dist-sys-lb   LoadBalancer   10.0.1.100   132.xxx.xxx.xxx   80:30080/TCP,9090:30090/TCP

# Access
export LB_IP=$(kubectl get svc dist-sys-lb -n production -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "API: http://$LB_IP"
echo "Metrics: http://$LB_IP:9090/metrics"
```

### Step 7: Setup Monitoring (Grafana + Prometheus)

```bash
# Deploy on VM-3 (or any node with label)
helm repo add grafana https://grafana.github.io/helm-charts
helm install monitoring grafana/kube-prometheus-stack \\
  --namespace monitoring --create-namespace \\
  --set prometheus.prometheusSpec.retention=7d \\
  --set grafana.enabled=true

# Port-forward for access
kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring
# Open: http://localhost:3000 (admin/prom-operator)
```

---

## Cost: $0 FOREVER

| Resource | Free Tier Limit | Usage | Cost |
|----------|----------------|-------|------|
| 3x ARM VMs | 4 VMs, 24GB RAM | 3 VMs, 18GB | **$0** |
| Block Storage | 200GB | 150GB (3x50GB) | **$0** |
| Load Balancer | 2 LBs | 1 LB | **$0** |
| Data Transfer | 10TB/month | ~100GB | **$0** |
| **TOTAL** | | | **$0/month** |

---

## Limitations

- **No automatic backups** (must script your own)
- **No managed etcd** (run etcd as pods or on VMs)
- **Manual scaling** (no auto-scaler in free tier)
- **No premium support**

---

## Troubleshooting

**"Out of host capacity" when creating ARM VMs:**
- ARM VMs are popular and may be unavailable
- Try different availability domain
- Or use AMD VMs (always available but less RAM)

**VMs stop unexpectedly:**
- Oracle may reclaim idle Always Free resources
- Keep VMs active with cron jobs

**Network connectivity issues:**
- Verify Security List rules (ingress/egress)
- Check route table has internet gateway