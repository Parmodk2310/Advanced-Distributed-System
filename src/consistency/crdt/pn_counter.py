"""PN-Counter: Increment/decrement counter CRDT."""

from typing import Dict
from .base import CRDT


class PNCounter(CRDT):
    """
    Positive-Negative counter supporting increment and decrement.
    
    Maintains two G-Counters: P (increments) and N (decrements).
    Value = P.value() - N.value()
    """
    
    def __init__(self, crdt_id: str, node_id: str):
        super().__init__(crdt_id, node_id)
        self.p: Dict[str, int] = {}  # Increments
        self.n: Dict[str, int] = {}  # Decrements
    
    def increment(self, amount: int = 1):
        self.p[self.node_id] = self.p.get(self.node_id, 0) + amount
    
    def decrement(self, amount: int = 1):
        self.n[self.node_id] = self.n.get(self.node_id, 0) + amount
    
    def value(self) -> int:
        return sum(self.p.values()) - sum(self.n.values())
    
    def merge(self, other: "PNCounter") -> "PNCounter":
        for node_id, count in other.p.items():
            self.p[node_id] = max(self.p.get(node_id, 0), count)
        for node_id, count in other.n.items():
            self.n[node_id] = max(self.n.get(node_id, 0), count)
        return self
    
    def to_dict(self) -> Dict:
        return {"crdt_id": self.crdt_id, "node_id": self.node_id, "type": "pn_counter", "p": self.p, "n": self.n}
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PNCounter":
        pnc = cls(data["crdt_id"], data["node_id"])
        pnc.p = data.get("p", {})
        pnc.n = data.get("n", {})
        return pnc