"""TLS encryption for TCP protocol."""

import ssl
import pathlib
from typing import Optional


class TLSSecurity:
    """
    TLS configuration for distributed node communication.
    
    Uses mutual TLS (mTLS) for authentication:
    - Server verifies client certificates
    - Client verifies server certificates
    - Both need valid CA-signed certs
    """
    
    def __init__(self, cert_dir: str = "certs"):
        self.cert_dir = pathlib.Path(cert_dir)
        self.ca_file = self.cert_dir / "ca.crt"
        self.cert_file = self.cert_dir / "server.crt"
        self.key_file = self.cert_dir / "server.key"
    
    def create_server_context(self) -> ssl.SSLContext:
        """Create SSL context for server with client cert verification."""
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=str(self.cert_file), keyfile=str(self.key_file))
        context.load_verify_locations(cafile=str(self.ca_file))
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = False
        # Strong cipher suites
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        return context
    
    def create_client_context(self) -> ssl.SSLContext:
        """Create SSL context for client with server cert verification."""
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.load_cert_chain(certfile=str(self.cert_file), keyfile=str(self.key_file))
        context.load_verify_locations(cafile=str(self.ca_file))
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = False
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        return context
    
    @staticmethod
    def generate_self_signed_certs(cert_dir: str = "certs"):
        """Generate self-signed CA and server certificates for development."""
        import subprocess
        import os
        
        path = pathlib.Path(cert_dir)
        path.mkdir(exist_ok=True)
        
        # Generate CA private key
        subprocess.run([
            "openssl", "genrsa", "-out", str(path / "ca.key"), "4096"
        ], check=True, capture_output=True)
        
        # Generate CA certificate
        subprocess.run([
            "openssl", "req", "-new", "-x509", "-days", "365",
            "-key", str(path / "ca.key"),
            "-out", str(path / "ca.crt"),
            "-subj", "/CN=distributed-system-ca"
        ], check=True, capture_output=True)
        
        # Generate server private key
        subprocess.run([
            "openssl", "genrsa", "-out", str(path / "server.key"), "4096"
        ], check=True, capture_output=True)
        
        # Generate server CSR
        subprocess.run([
            "openssl", "req", "-new",
            "-key", str(path / "server.key"),
            "-out", str(path / "server.csr"),
            "-subj", "/CN=distributed-node"
        ], check=True, capture_output=True)
        
        # Sign server cert with CA
        subprocess.run([
            "openssl", "x509", "-req", "-days", "365",
            "-in", str(path / "server.csr"),
            "-CA", str(path / "ca.crt"),
            "-CAkey", str(path / "ca.key"),
            "-CAcreateserial",
            "-out", str(path / "server.crt")
        ], check=True, capture_output=True)
        
        print(f"TLS certificates generated in {cert_dir}/")