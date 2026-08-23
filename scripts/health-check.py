#!/usr/bin/env python3
"""Health check script for load balancers and monitoring."""

import sys
import socket
import struct
import argparse

from src.protocol.message import Message, MessageType


def check_node_health(host: str, port: int, timeout: float = 5.0) -> bool:
    """Send health check to a node and verify response."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        
        msg = Message(MessageType.HEALTH_CHECK, "health-checker", b"")
        sock.sendall(msg.serialize())
        
        # Read response header
        header = sock.recv(4)
        if len(header) < 4:
            return False
        
        sender_len = struct.unpack("!B", sock.recv(1))[0]
        sock.recv(sender_len)
        corr_len = struct.unpack("!B", sock.recv(1))[0]
        sock.recv(corr_len)
        sock.recv(9)  # timestamp + ttl
        vc_len = struct.unpack("!I", sock.recv(4))[0]
        sock.recv(vc_len)
        payload_len = struct.unpack("!I", sock.recv(4))[0]
        payload = sock.recv(payload_len)
        
        import json
        data = json.loads(payload.decode())
        
        sock.close()
        
        status = data.get("status", "unknown")
        load = data.get("load", 1.0)
        
        print(f"✅ {host}:{port} - Status: {status}, Load: {load:.1%}")
        return status == "healthy" and load < 0.95
        
    except Exception as e:
        print(f"❌ {host}:{port} - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Health check distributed nodes")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--nodes", type=int, default=1)
    args = parser.parse_args()
    
    healthy = 0
    for i in range(args.nodes):
        if check_node_health(args.host, args.port + i):
            healthy += 1
    
    print(f"\\n{healthy}/{args.nodes} nodes healthy")
    sys.exit(0 if healthy == args.nodes else 1)


if __name__ == "__main__":
    main()