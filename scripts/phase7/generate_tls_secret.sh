#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

phase7_require_command openssl
phase7_require_command kubectl
phase7_prepare_work_dir

readonly TLS_DIR="$PHASE7_WORK_DIR/tls"
readonly TLS_DAYS="${PHASE7_TLS_DAYS:-7}"
readonly SECRET_NAME="${PHASE7_TLS_SECRET:-distsys-node-tls}"

rm -rf "$TLS_DIR"
mkdir -p "$TLS_DIR/ca"
chmod 700 "$TLS_DIR" "$TLS_DIR/ca"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out "$TLS_DIR/ca/ca.key" >/dev/null 2>&1
chmod 600 "$TLS_DIR/ca/ca.key"
openssl req -x509 -new -sha256 -days "$TLS_DAYS" \
  -key "$TLS_DIR/ca/ca.key" \
  -subj "/CN=Phase 7 Ephemeral Development CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -out "$TLS_DIR/ca/ca.crt" >/dev/null 2>&1

issue_identity() {
  local identity="$1"
  local identity_dir="$TLS_DIR/$identity"
  mkdir -p "$identity_dir"
  chmod 700 "$identity_dir"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
    -out "$identity_dir/tls.key" >/dev/null 2>&1
  chmod 600 "$identity_dir/tls.key"
  openssl req -new -sha256 \
    -key "$identity_dir/tls.key" \
    -subj "/CN=$identity" \
    -out "$identity_dir/tls.csr" >/dev/null 2>&1
  openssl x509 -req -sha256 -days "$TLS_DAYS" \
    -in "$identity_dir/tls.csr" \
    -CA "$TLS_DIR/ca/ca.crt" \
    -CAkey "$TLS_DIR/ca/ca.key" \
    -CAcreateserial \
    -extfile <(printf '%s\n' \
      'basicConstraints=CA:FALSE' \
      'keyUsage=digitalSignature,keyEncipherment' \
      'extendedKeyUsage=serverAuth,clientAuth' \
      "subjectAltName=DNS:$identity,DNS:$identity.$PHASE7_RELEASE-distributed-system-headless,DNS:$identity.$PHASE7_RELEASE-distributed-system-headless.$PHASE7_NAMESPACE.svc") \
    -out "$identity_dir/tls.crt" >/dev/null 2>&1
  rm -f "$identity_dir/tls.csr"
}

identities=()
for ordinal in 0 1 2; do
  identity="$PHASE7_RELEASE-distributed-system-$ordinal"
  issue_identity "$identity"
  identities+=("$identity")
done
issue_identity "phase7-client"

secret_args=(
  create secret generic "$SECRET_NAME"
  --namespace "$PHASE7_NAMESPACE"
  --from-file="ca.crt=$TLS_DIR/ca/ca.crt"
)
for identity in "${identities[@]}"; do
  secret_args+=(
    --from-file="$identity.crt=$TLS_DIR/$identity/tls.crt"
    --from-file="$identity.key=$TLS_DIR/$identity/tls.key"
  )
done

kubectl "${secret_args[@]}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
printf 'ephemeral Phase 7 TLS Secret applied in namespace %s\n' "$PHASE7_NAMESPACE"
