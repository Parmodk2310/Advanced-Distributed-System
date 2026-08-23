"""Base class for Conflict-free Replicated Data Types."""

from abc import ABC, abstractmethod
from typing import Any, Dict
import json


class CRDT(ABC):
    """Abstract base for all CRDT implementations."""
    
    def __init__(self, crdt_id: str, node_id: str):
        self.crdt_id = crdt_id
        self.node_id = node_id
    
    @abstractmethod
    def merge(self, other: "CRDT") -> "CRDT":
        """Merge another CRDT state into this one. Must be commutative, associative, idempotent."""
        pass
    
    @abstractmethod
    def to_dict(self) -> Dict:
        pass
    
    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict) -> "CRDT":
        pass
    
    def serialize(self) -> bytes:
        return json.dumps(self.to_dict()).encode('utf-8')
    
    @classmethod
    def deserialize(cls, data: bytes) -> "CRDT":
        return cls.from_dict(json.loads(data.decode('utf-8')))