#!/bin/bash
set -e

CERT_DIR="$(dirname "$0")"
cd "$CERT_DIR"

# Skip if certs already exist
if [ -f "server.crt" ] && [ -f "server.key" ] && [ -f "ca.crt" ]; then
    echo "TLS certificates already exist in $CERT_DIR"
    exit 0
fi

echo "Generating self-signed TLS certificates..."

# CA
openssl genrsa -out ca.key 4096 2>/dev/null
openssl req -new -x509 -days 365 -key ca.key -out ca.crt -subj "/CN=distributed-system-ca"

# Server
openssl genrsa -out server.key 4096 2>/dev/null
openssl req -new -key server.key -out server.csr -subj "/CN=distributed-node"
openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt

# Client (for mTLS)
openssl genrsa -out client.key 4096 2>/dev/null
openssl req -new -key client.key -out client.csr -subj "/CN=distributed-client"
openssl x509 -req -days 365 -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt

rm -f *.csr *.srl
echo "✅ Certificates generated in $CERT_DIR"