# 🛤️ Render / Railway Free Tier Deployment

## Why Render/Railway?

**Render Free Tier:**
- **Web services**: 512MB RAM, unlimited bandwidth
- **Background workers**: 512MB RAM
- **PostgreSQL**: 1GB storage (can replace etcd for small deployments)
- **Custom domains + TLS**: Free
- **Auto-deploy from Git**: Free

**Railway Free Tier:**
- **$5 credit/month** (~500 hours of 512MB container)
- **Automatic scaling**
- **PostgreSQL, Redis, MongoDB**: Included
- **Git-based deploys**

**Best for:** Rapid prototyping, small teams, Git-based workflows.

---

## Render Deployment

### Step 1: Create render.yaml

```yaml
# render.yaml
services:
  - type: pserv
    name: dist-node-0
    runtime: docker
    dockerfilePath: ./Dockerfile.render
    envVars:
      - key: NODE_ID
        value: node-0
      - key: NODE_PORT
        value: "8000"
      - key: PEERS
        value: "dist-node-1:8000,dist-node-2:8000"
      - key: USE_TLS
        value: "false"
      - key: MAX_WORKERS
        value: "1"
    disk:
      name: etcd-data
      mountPath: /etcd-data
      sizeGB: 1

  - type: pserv
    name: dist-node-1
    runtime: docker
    dockerfilePath: ./Dockerfile.render
    envVars:
      - key: NODE_ID
        value: node-1
      - key: NODE_PORT
        value: "8000"
      - key: PEERS
        value: "dist-node-0:8000,dist-node-2:8000"
      - key: USE_TLS
        value: "false"
      - key: MAX_WORKERS
        value: "1"
    disk:
      name: etcd-data
      mountPath: /etcd-data
      sizeGB: 1

  - type: pserv
    name: dist-node-2
    runtime: docker
    dockerfilePath: ./Dockerfile.render
    envVars:
      - key: NODE_ID
        value: node-2
      - key: NODE_PORT
        value: "8000"
      - key: PEERS
        value: "dist-node-0:8000,dist-node-1:8000"
      - key: USE_TLS
        value: "false"
      - key: MAX_WORKERS
        value: "1"
    disk:
      name: etcd-data
      mountPath: /etcd-data
      sizeGB: 1

  - type: web
    name: dist-sys-api
    runtime: docker
    dockerfilePath: ./Dockerfile.render
    envVars:
      - key: NODE_ID
        value: node-api
      - key: NODE_PORT
        value: "8000"
      - key: PEERS
        value: "dist-node-0:8000,dist-node-1:8000,dist-node-2:8000"
    healthCheckPath: /health
```

### Step 2: Create Dockerfile.render

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y \\
    gcc \\
    libffi-dev \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "src"]
```

### Step 3: Deploy

```bash
# Push to GitHub
git init
git add .
git commit -m "Initial commit"
git push origin main

# Connect to Render
# 1. Go to render.com
# 2. Create Blueprint from repo
# 3. Select render.yaml
# 4. Deploy

# Or use Render CLI
npm install -g @render/cli
render blueprint apply
```

---

## Railway Deployment

### Step 1: Create railway.json

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile.render"
  },
  "deploy": {
    "startCommand": "python -m src",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

### Step 2: Deploy

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Init project
railway init

# Add services (3 nodes)
railway add --service node-0 --env NODE_ID=node-0
railway add --service node-1 --env NODE_ID=node-1
railway add --service node-2 --env NODE_ID=node-2

# Deploy
railway up

# View logs
railway logs

# Add custom domain
railway domain
```

---

## Cost

| Platform | Free Tier | Actual Cost |
|----------|-----------|-------------|
| **Render** | 3x 512MB services + 1GB disk each | **$0** |
| **Railway** | $5 credit/month (~500 hours) | **$0** (within credit) |

---

## Limitations

- **Services sleep after 15 min inactivity** (Render free tier)
- **512MB RAM** (must optimize for low memory)
- **No UDP support** (gossip protocol must use TCP fallback)
- **No persistent volumes** on Railway (use external DB)