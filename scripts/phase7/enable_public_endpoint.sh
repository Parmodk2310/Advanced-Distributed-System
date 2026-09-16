#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
phase7_require_command kubectl
cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ${PHASE7_RELEASE}-temporary-public-ingress
  namespace: ${PHASE7_NAMESPACE}
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: distributed-system
      app.kubernetes.io/instance: ${PHASE7_RELEASE}
  policyTypes: [Ingress]
  ingress:
    - ports:
        - protocol: TCP
          port: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: ${PHASE7_RELEASE}-public
  namespace: ${PHASE7_NAMESPACE}
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-additional-resource-tags: "Phase=7,Environment=phase7-demo"
spec:
  type: LoadBalancer
  selector:
    app.kubernetes.io/name: distributed-system
    app.kubernetes.io/instance: ${PHASE7_RELEASE}
  ports:
    - name: protocol
      port: 8000
      targetPort: protocol
EOF
kubectl -n "$PHASE7_NAMESPACE" get service "${PHASE7_RELEASE}-public"
