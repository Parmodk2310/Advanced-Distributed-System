"""G-Counter: Grow-only counter CRDT."""

from typing import Dict
from .base import CRDT


class GCounter(CRDT):
    """
    Grow-only counter.
    
    Each node maintains its own increment count.
    Total value = sum of all node counters.
    Merge: component-wise max.
    """
    
    def __init__(self, crdt_id: str, node_id: str):
        super().__init__(crdt_id, node_id)
        self.counters: Dict[str, int] = {}
    
    def increment(self, amount: int = 1):
        self.counters[self.node_id] = self.counters.get(self.node_id, 0) + amount
    
    def value(self) -> int:
        return sum(self.counters.values())
    
    def merge(self, other: "GCounter") -> "GCounter":
        for node_id, count in other.counters.items():
            self.counters[node_id] = max(self.counters.get(node_id, 0), count)
        return self
    
    def to_dict(self) -> Dict:
        return {"crdt_id": self.crdt_id, "node_id": self.node_id, "type": "g_counter", "counters": self.counters}
    
    @classmethod
    def from_dict(cls, data: Dict) -> "GCounter":
        gc = cls(data["crdt_id"], data["node_id"])
        gc.counters = data.get("counters", {})
        return gc