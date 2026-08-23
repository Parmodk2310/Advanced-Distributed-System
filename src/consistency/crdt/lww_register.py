"""LWW-Register: Last-Write-Wins register CRDT."""

from typing import Dict, Any, Optional
import time
from .base import CRDT


class LWWRegister(CRDT):
    """
    Last-Write-Wins register.
    
    Each write is tagged with a timestamp. On merge, the value with
    the highest timestamp wins. Ties broken by node_id lexicographically.
    """
    
    def __init__(self, crdt_id: str, node_id: str):
        super().__init__(crdt_id, node_id)
        self.value: Any = None
        self.timestamp: float = 0.0
        self.writer_id: str = ""
    
    def set(self, value: Any):
        self.value = value
        self.timestamp = time.time()
        self.writer_id = self.node_id
    
    def get(self) -> Any:
        return self.value
    
    def merge(self, other: "LWWRegister") -> "LWWRegister":
        if other.timestamp > self.timestamp:
            self.value = other.value
            self.timestamp = other.timestamp
            self.writer_id = other.writer_id
        elif other.timestamp == self.timestamp and other.writer_id > self.writer_id:
            self.value = other.value
            self.writer_id = other.writer_id
        return self
    
    def to_dict(self) -> Dict:
        return {
            "crdt_id": self.crdt_id, "node_id": self.node_id, "type": "lww_register",
            "value": self.value, "timestamp": self.timestamp, "writer_id": self.writer_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "LWWRegister":
        reg = cls(data["crdt_id"], data["node_id"])
        reg.value = data.get("value")
        reg.timestamp = data.get("timestamp", 0)
        reg.writer_id = data.get("writer_id", "")
        return reg
'''

or_set = '''"""OR-Set: Observed-Removed Set CRDT."""

from typing import Dict, Set, Any
import uuid
from .base import CRDT


class ORSet(CRDT):
    """
    Observed-Removed Set (Add-Wins OR-Set).
    
    Each element has a set of unique tags. Add generates new tags.
    Remove records observed tags. An element is present if it has
    tags that were not observed by any remove.
    """
    
    def __init__(self, crdt_id: str, node_id: str):
        super().__init__(crdt_id, node_id)
        self.adds: Dict[Any, Set[str]] = {}   # element -> set of tags
        self.removes: Dict[Any, Set[str]] = {}  # element -> set of observed tags
    
    def add(self, element: Any):
        tag = f"{self.node_id}-{uuid.uuid4().hex[:8]}"
        if element not in self.adds:
            self.adds[element] = set()
        self.adds[element].add(tag)
    
    def remove(self, element: Any):
        if element in self.adds:
            self.removes[element] = self.removes.get(element, set()) | self.adds[element]
    
    def contains(self, element: Any) -> bool:
        if element not in self.adds:
            return False
        effective = self.adds[element] - self.removes.get(element, set())
        return len(effective) > 0
    
    def value(self) -> Set[Any]:
        return {e for e in self.adds if self.contains(e)}
    
    def merge(self, other: "ORSet") -> "ORSet":
        for elem, tags in other.adds.items():
            self.adds[elem] = self.adds.get(elem, set()) | tags
        for elem, tags in other.removes.items():
            self.removes[elem] = self.removes.get(elem, set()) | tags
        return self
    
    def to_dict(self) -> Dict:
        return {
            "crdt_id": self.crdt_id, "node_id": self.node_id, "type": "or_set",
            "adds": {str(k): list(v) for k, v in self.adds.items()},
            "removes": {str(k): list(v) for k, v in self.removes.items()}
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ORSet":
        s = cls(data["crdt_id"], data["node_id"])
        s.adds = {k: set(v) for k, v in data.get("adds", {}).items()}
        s.removes = {k: set(v) for k, v in data.get("removes", {}).items()}
        return s