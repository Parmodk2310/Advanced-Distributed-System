
"""etcd integration for persistent cluster state."""

import json
import asyncio
from typing import Optional, Dict, Any, List


class EtcdStateStore:
    """
    Persist gossip state and CRDTs to etcd for cold starts.
    
    Uses etcd's lease mechanism for ephemeral membership entries
    and transactional writes for CRDT state.
    """
    
    def __init__(self, endpoints: List[str] = None, prefix: str = "/dist-sys"):
        self.endpoints = endpoints or ["http://localhost:2379"]
        self.prefix = prefix
        self._client = None
        self._lease = None
        
    async def connect(self):
        """Connect to etcd cluster."""
        try:
            import etcd3
            self._client = etcd3.client(host="localhost", port=2379)
            # Create lease for ephemeral keys (TTL 30s)
            self._lease = self._client.lease(30)
        except ImportError:
            raise RuntimeError("etcd3 not installed. Run: pip install etcd3")
    
    async def register_member(self, node_id: str, host: str, port: int, metadata: Dict = None):
        """Register node membership with ephemeral lease."""
        if not self._client:
            return
        key = f"{self.prefix}/members/{node_id}"
        value = json.dumps({"host": host, "port": port, "metadata": metadata or {}})
        self._client.put(key, value, lease=self._lease)
    
    async def get_members(self) -> Dict[str, Dict]:
        """Retrieve all registered members."""
        if not self._client:
            return {}
        members = {}
        for value, metadata in self._client.get_prefix(f"{self.prefix}/members/"):
            key = metadata.key.decode().split("/")[-1]
            members[key] = json.loads(value.decode())
        return members
    
    async def save_crdt(self, crdt_id: str, state: bytes):
        """Persist CRDT state."""
        if not self._client:
            return
        key = f"{self.prefix}/crdts/{crdt_id}"
        self._client.put(key, state)
    
    async def load_crdt(self, crdt_id: str) -> Optional[bytes]:
        """Load CRDT state."""
        if not self._client:
            return None
        key = f"{self.prefix}/crdts/{crdt_id}"
        value, _ = self._client.get(key)
        return value
    
    async def save_vector_clock(self, node_id: str, vc_data: bytes):
        """Persist vector clock."""
        if not self._client:
            return
        key = f"{self.prefix}/clocks/{node_id}"
        self._client.put(key, vc_data)
    
    async def watch_members(self, callback):
        """Watch for membership changes."""
        if not self._client:
            return
        events_iterator, cancel = self._client.watch_prefix(f"{self.prefix}/members/")
        for event in events_iterator:
            await callback(event)
    
    async def close(self):
        if self._client:
            self._client.close()
