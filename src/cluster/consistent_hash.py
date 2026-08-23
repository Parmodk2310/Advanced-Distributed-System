"""Consistent hashing ring for data distribution."""

import hashlib
import heapq
from typing import Dict, List, Set, Optional
from bisect import bisect_right


class ConsistentHashRing:
    """Consistent hashing with virtual nodes for even distribution."""
    
    def __init__(self, replicas: int = 150):
        self.replicas = replicas
        self.ring: Dict[int, str] = {}
        self.sorted_keys: List[int] = []
        self.nodes: Set[str] = set()
        
    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)
    
    def add_node(self, node_id: str):
        if node_id in self.nodes:
            return
        self.nodes.add(node_id)
        for i in range(self.replicas):
            key = self._hash(f"{node_id}:{i}")
            self.ring[key] = node_id
            heapq.heappush(self.sorted_keys, key)
        self.sorted_keys.sort()
        
    def remove_node(self, node_id: str):
        if node_id not in self.nodes:
            return
        self.nodes.remove(node_id)
        new_ring = {}
        new_keys = []
        for k, v in self.ring.items():
            if v != node_id:
                new_ring[k] = v
                new_keys.append(k)
        self.ring = new_ring
        self.sorted_keys = sorted(new_keys)
        
    def get_node(self, data_key: str) -> Optional[str]:
        if not self.ring:
            return None
        h = self._hash(data_key)
        idx = bisect_right(self.sorted_keys, h) % len(self.sorted_keys)
        return self.ring[self.sorted_keys[idx]]
    
    def get_nodes(self, data_key: str, n: int = 3) -> List[str]:
        if not self.ring:
            return []
        h = self._hash(data_key)
        idx = bisect_right(self.sorted_keys, h) % len(self.sorted_keys)
        results = []
        seen = set()
        for i in range(len(self.sorted_keys)):
            node = self.ring[self.sorted_keys[(idx + i) % len(self.sorted_keys)]]
            if node not in seen:
                seen.add(node)
                results.append(node)
                if len(results) >= n:
                    break
        return results