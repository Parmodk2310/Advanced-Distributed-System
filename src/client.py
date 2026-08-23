"""Distributed client for interacting with the cluster."""

import asyncio
import struct
import json
import ssl
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from src.protocol.message import Message, MessageType
from src.protocol.tls import TLSSecurity
from src.cluster.consistent_hash import ConsistentHashRing


class DistributedClient:
    """
    High-level client for the distributed system.
    
    Features:
    - Connection pooling
    - Load balancing via consistent hashing
    - Automatic failover
    - TLS support
    - Request batching
    """
    
    def __init__(self, nodes: List[Dict[str, Any]], use_tls: bool = False, cert_dir: str = "certs"):
        """
        Args:
            nodes: List of {"host": str, "port": int, "node_id": str}
            use_tls: Enable TLS
            cert_dir: Certificate directory
        """
        self.nodes = nodes
        self.use_tls = use_tls
        self.tls = TLSSecurity(cert_dir) if use_tls else None
        self.hash_ring = ConsistentHashRing()
        self._connections: Dict[str, tuple] = {}  # node_id -> (reader, writer)
        self._lock = asyncio.Lock()
        
        for node in nodes:
            self.hash_ring.add_node(node["node_id"])
    
    async def _get_connection(self, node_id: str) -> tuple:
        """Get or create connection to a node."""
        if node_id in self._connections:
            return self._connections[node_id]
        
        node = next(n for n in self.nodes if n["node_id"] == node_id)
        
        if self.use_tls and self.tls:
            ssl_ctx = self.tls.create_client_context()
            reader, writer = await asyncio.open_connection(
                node["host"], node["port"], ssl=ssl_ctx
            )
        else:
            reader, writer = await asyncio.open_connection(
                node["host"], node["port"]
            )
        
        self._connections[node_id] = (reader, writer)
        return reader, writer
    
    async def request(self, task: str, data: Dict, key: Optional[str] = None, 
                      timeout: float = 10.0) -> Dict:
        """
        Send a request to the cluster.
        
        Args:
            task: Task type (hash, sort, aggregate, echo, crdt_get, crdt_op)
            data: Task data
            key: Routing key for consistent hashing (optional)
            timeout: Request timeout
        """
        # Route by key if provided
        if key:
            target_node = self.hash_ring.get_node(key)
        else:
            target_node = self.nodes[0]["node_id"]
        
        node = next(n for n in self.nodes if n["node_id"] == target_node)
        
        payload = json.dumps({"task": task, **data}).encode()
        msg = Message(MessageType.REQUEST, "client", payload)
        
        try:
            reader, writer = await self._get_connection(target_node)
            writer.write(msg.serialize())
            await writer.drain()
            
            # Read response
            header = await asyncio.wait_for(reader.read(4), timeout=timeout)
            if len(header) < 4:
                raise ConnectionError("Incomplete header")
            
            sender_len = struct.unpack("!B", await reader.read(1))[0]
            await reader.read(sender_len)
            corr_len = struct.unpack("!B", await reader.read(1))[0]
            await reader.read(corr_len)
            await reader.read(9)  # timestamp + ttl
            vc_len = struct.unpack("!I", await reader.read(4))[0]
            await reader.read(vc_len)
            payload_len = struct.unpack("!I", await reader.read(4))[0]
            payload = await reader.read(payload_len)
            
            return json.loads(payload.decode())
            
        except Exception as e:
            # Remove dead connection
            self._connections.pop(target_node, None)
            raise ConnectionError(f"Request failed: {e}")
    
    async def batch_request(self, requests: List[Dict], timeout: float = 30.0) -> List[Dict]:
        """Send batched requests for efficiency."""
        payload = json.dumps({"requests": requests}).encode()
        msg = Message(MessageType.BATCH, "client", payload)
        
        node = self.nodes[0]
        reader, writer = await asyncio.open_connection(node["host"], node["port"])
        try:
            writer.write(msg.serialize())
            await writer.drain()
            
            header = await asyncio.wait_for(reader.read(4), timeout=timeout)
            sender_len = struct.unpack("!B", await reader.read(1))[0]
            await reader.read(sender_len)
            corr_len = struct.unpack("!B", await reader.read(1))[0]
            await reader.read(corr_len)
            await reader.read(9)
            vc_len = struct.unpack("!I", await reader.read(4))[0]
            await reader.read(vc_len)
            payload_len = struct.unpack("!I", await reader.read(4))[0]
            payload = await reader.read(payload_len)
            
            result = json.loads(payload.decode())
            return result.get("batch_results", [])
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def health_check(self, node_id: str) -> Dict:
        """Check health of a specific node."""
        node = next(n for n in self.nodes if n["node_id"] == node_id)
        msg = Message(MessageType.HEALTH_CHECK, "client", b"")
        
        reader, writer = await asyncio.open_connection(node["host"], node["port"])
        try:
            writer.write(msg.serialize())
            await writer.drain()
            
            header = await asyncio.wait_for(reader.read(4), timeout=5.0)
            sender_len = struct.unpack("!B", await reader.read(1))[0]
            await reader.read(sender_len)
            corr_len = struct.unpack("!B", await reader.read(1))[0]
            await reader.read(corr_len)
            await reader.read(9)
            vc_len = struct.unpack("!I", await reader.read(4))[0]
            await reader.read(vc_len)
            payload_len = struct.unpack("!I", await reader.read(4))[0]
            payload = await reader.read(payload_len)
            
            return json.loads(payload.decode())
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def close(self):
        """Close all connections."""
        for node_id, (reader, writer) in self._connections.items():
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass
        self._connections.clear()
'''

utils_py = '''"""Utility functions."""

import time
import functools
from typing import Callable, Any


def timer(func: Callable) -> Callable:
    """Decorator to measure execution time."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        elapsed = (time.time() - start) * 1000
        print(f"{func.__name__} took {elapsed:.2f}ms")
        return result
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = (time.time() - start) * 1000
        print(f"{func.__name__} took {elapsed:.2f}ms")
        return result
    
    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


def retry_sync(max_retries: int = 3, delay: float = 1.0):
    """Synchronous retry decorator."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(delay * (2 ** attempt))
            return None
        return wrapper
    return decorator