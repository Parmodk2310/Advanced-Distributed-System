#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-certs/generated}"
DAYS="${CERT_DAYS:-30}"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/ca"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$OUT_DIR/ca/ca.key" >/dev/null 2>&1
chmod 600 "$OUT_DIR/ca/ca.key"
cat > "$OUT_DIR/ca/ca.cnf" <<'EOF'
[req]
distinguished_name = dn
x509_extensions = v3_ca
prompt = no

[dn]
CN = Phase5 Development CA

[v3_ca]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
EOF

openssl req -x509 -new -sha256 -days "$DAYS" \
  -key "$OUT_DIR/ca/ca.key" \
  -config "$OUT_DIR/ca/ca.cnf" \
  -extensions v3_ca \
  -out "$OUT_DIR/ca/ca.crt" >/dev/null 2>&1
rm -f "$OUT_DIR/ca/ca.cnf"

issue_cert() {
  local name="$1"
  local dir="$OUT_DIR/$name"
  mkdir -p "$dir"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$dir/node.key" >/dev/null 2>&1
  chmod 600 "$dir/node.key"
  openssl req -new -sha256 \
    -key "$dir/node.key" \
    -subj "/CN=$name" \
    -out "$dir/node.csr" >/dev/null 2>&1
  cat > "$dir/ext.cnf" <<EOF
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth,clientAuth
subjectAltName=DNS:$name,IP:127.0.0.1
EOF
  openssl x509 -req -sha256 -days "$DAYS" \
    -in "$dir/node.csr" \
    -CA "$OUT_DIR/ca/ca.crt" \
    -CAkey "$OUT_DIR/ca/ca.key" \
    -CAcreateserial \
    -extfile "$dir/ext.cnf" \
    -out "$dir/node.crt" >/dev/null 2>&1
  rm -f "$dir/node.csr" "$dir/ext.cnf"
}

for identity in node-0 node-1 node-2 crdt-client client; do
  issue_cert "$identity"
done

echo "DEVELOPMENT ONLY certificates generated under $OUT_DIR"
