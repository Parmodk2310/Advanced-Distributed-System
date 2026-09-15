#!/usr/bin/env bash
set -euo pipefail
umask 077

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

for tool in openssl kubectl; do
  require_tool "$tool"
done

safe_remove_dir "$PHASE7_TLS_DIR"
mkdir -p "$PHASE7_TLS_DIR"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048   -out "$PHASE7_TLS_DIR/ca.key" >/dev/null 2>&1
chmod 600 "$PHASE7_TLS_DIR/ca.key"

openssl req -x509 -new -sha256 -days 7   -key "$PHASE7_TLS_DIR/ca.key"   -subj "/CN=Phase 7 Ephemeral Development CA"   -out "$PHASE7_TLS_DIR/ca.crt" >/dev/null 2>&1

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048   -out "$PHASE7_TLS_DIR/tls.key" >/dev/null 2>&1
chmod 600 "$PHASE7_TLS_DIR/tls.key"

cat > "$PHASE7_TLS_DIR/ext.cnf" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth,clientAuth
subjectAltName=DNS:phase7-distributed-system-0,DNS:phase7-distributed-system-1,DNS:phase7-distributed-system-2,DNS:phase7-distributed-system-headless,DNS:*.phase7-distributed-system-headless.$PHASE7_NAMESPACE.svc.cluster.local
EOF

openssl req -new -sha256   -key "$PHASE7_TLS_DIR/tls.key"   -subj "/CN=phase7-distributed-system"   -out "$PHASE7_TLS_DIR/tls.csr" >/dev/null 2>&1

openssl x509 -req -sha256 -days 7   -in "$PHASE7_TLS_DIR/tls.csr"   -CA "$PHASE7_TLS_DIR/ca.crt"   -CAkey "$PHASE7_TLS_DIR/ca.key"   -CAcreateserial   -extfile "$PHASE7_TLS_DIR/ext.cnf"   -out "$PHASE7_TLS_DIR/tls.crt" >/dev/null 2>&1

kubectl -n "$PHASE7_NAMESPACE" create secret generic distsys-node-tls   --from-file=ca.crt="$PHASE7_TLS_DIR/ca.crt"   --from-file=tls.crt="$PHASE7_TLS_DIR/tls.crt"   --from-file=tls.key="$PHASE7_TLS_DIR/tls.key"   --dry-run=client -o yaml | kubectl apply -f -

rm -f -- "$PHASE7_TLS_DIR/tls.csr" "$PHASE7_TLS_DIR/ext.cnf"   "$PHASE7_TLS_DIR/ca.srl"
