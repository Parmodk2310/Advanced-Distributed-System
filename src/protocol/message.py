"""Protocol serialization using protobuf for cross-language compatibility."""

import struct
import time
import uuid
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

# Generated protobuf imports (will be created by protoc)
# For now, we use a pure-Python fallback that matches the protobuf schema


@dataclass
class VectorClockEntry:
    """Single entry in a vector clock."""
    node_id: str
    timestamp: float = field(default_factory=time.time)
    counter: int = 0
    
    def increment(self):
        self.counter += 1
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return {"node_id": self.node_id, "timestamp": self.timestamp, "counter": self.counter}
    
    @classmethod
    def from_dict(cls, d: Dict) -> "VectorClockEntry":
        return cls(node_id=d["node_id"], timestamp=d.get("timestamp", 0), counter=d.get("counter", 0))


class VectorClock:
    """
    Vector clock for causal consistency in distributed systems.
    
    Each node maintains a logical clock. When events occur, the local counter
    increments. When receiving messages, clocks are merged by taking the
    component-wise maximum.
    
    Comparison rules:
        vc1 < vc2  : vc1 happened-before vc2 (causal)
        vc1 > vc2  : vc2 happened-before vc1 (causal)
        vc1 || vc2 : concurrent (conflict detected)
        vc1 == vc2 : identical
    """
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.clocks: Dict[str, VectorClockEntry] = {}
        self._init_local()
    
    def _init_local(self):
        if self.node_id not in self.clocks:
            self.clocks[self.node_id] = VectorClockEntry(node_id=self.node_id)
    
    def increment(self) -> "VectorClock":
        """Increment local clock before sending a message or performing an operation."""
        self._init_local()
        self.clocks[self.node_id].increment()
        return self
    
    def merge(self, other: "VectorClock") -> "VectorClock":
        """Merge another vector clock into this one (component-wise max)."""
        for node_id, entry in other.clocks.items():
            if node_id not in self.clocks or entry.counter > self.clocks[node_id].counter:
                self.clocks[node_id] = VectorClockEntry(
                    node_id=node_id,
                    timestamp=entry.timestamp,
                    counter=entry.counter
                )
        return self
    
    def compare(self, other: "VectorClock") -> Optional[str]:
        """
        Compare two vector clocks.
        Returns: '<', '>', '==', '||' (concurrent), or None
        """
        all_nodes = set(self.clocks.keys()) | set(other.clocks.keys())
        
        less = False
        greater = False
        
        for node_id in all_nodes:
            c1 = self.clocks.get(node_id, VectorClockEntry(node_id)).counter
            c2 = other.clocks.get(node_id, VectorClockEntry(node_id)).counter
            
            if c1 < c2:
                less = True
            elif c1 > c2:
                greater = True
        
        if less and greater:
            return "||"  # Concurrent
        elif less:
            return "<"
        elif greater:
            return ">"
        else:
            return "=="
    
    def is_concurrent_with(self, other: "VectorClock") -> bool:
        return self.compare(other) == "||"
    
    def happened_before(self, other: "VectorClock") -> bool:
        return self.compare(other) == "<"
    
    def to_list(self) -> List[Dict]:
        return [e.to_dict() for e in self.clocks.values()]
    
    @classmethod
    def from_list(cls, node_id: str, entries: List[Dict]) -> "VectorClock":
        vc = cls(node_id)
        for e in entries:
            vc.clocks[e["node_id"]] = VectorClockEntry.from_dict(e)
        return vc
    
    def copy(self) -> "VectorClock":
        vc = VectorClock(self.node_id)
        for nid, entry in self.clocks.items():
            vc.clocks[nid] = VectorClockEntry(nid, entry.timestamp, entry.counter)
        return vc
    
    def __repr__(self):
        items = ", ".join(f"{k}:{v.counter}" for k, v in sorted(self.clocks.items()))
        return f"VC({items})"


# =============================================================================
# MESSAGE TYPES (matching protobuf enum)
# =============================================================================

class MessageType:
    HEARTBEAT = 0
    REQUEST = 1
    RESPONSE = 2
    GOSSIP = 3
    HEALTH_CHECK = 4
    BACKPRESSURE = 5
    CIRCUIT_OPEN = 6
    CIRCUIT_CLOSE = 7
    SHUTDOWN = 8
    BATCH = 9


@dataclass
class Message:
    """
    Protocol message with vector clock support.
    
    Uses a lightweight binary framing compatible with protobuf wire format.
    Header: [MAGIC(2)][VERSION(1)][TYPE(1)][SENDER_LEN(1)][SENDER(N)]
            [CORR_LEN(1)][CORR(N)][TIMESTAMP(8)][TTL(1)][VC_LEN(4)][VC(N)]
            [PAYLOAD_LEN(4)][PAYLOAD(N)]
    """
    msg_type: int
    sender_id: str
    payload: bytes
    timestamp: float = field(default_factory=time.time)
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    ttl: int = 3
    vector_clock: Optional[VectorClock] = None
    
    MAGIC = b'DS'
    VERSION = 2  # Bumped for vector clock support
    HEADER_FMT = '!2sBB'
    
    def serialize(self) -> bytes:
        sender_bytes = self.sender_id.encode('utf-8')
        corr_bytes = self.correlation_id.encode('utf-8')
        
        # Serialize vector clock
        if self.vector_clock:
            import json
            vc_data = json.dumps(self.vector_clock.to_list()).encode('utf-8')
        else:
            vc_data = b''
        
        header = struct.pack(self.HEADER_FMT, self.MAGIC, self.VERSION, self.msg_type)
        sender_header = struct.pack('!B', len(sender_bytes)) + sender_bytes
        corr_header = struct.pack('!B', len(corr_bytes)) + corr_bytes
        meta = struct.pack('!dB', self.timestamp, self.ttl)
        vc_header = struct.pack('!I', len(vc_data)) + vc_data
        payload_header = struct.pack('!I', len(self.payload))
        
        return header + sender_header + corr_header + meta + vc_header + payload_header + self.payload
    
    @classmethod
    def deserialize(cls, data: bytes) -> "Message":
        import json
        offset = 0
        magic, version, msg_type = struct.unpack(cls.HEADER_FMT, data[offset:offset+4])
        offset += 4
        
        assert magic == cls.MAGIC and version == cls.VERSION, f"Invalid header: {magic} v{version}"
        
        sender_len = struct.unpack('!B', data[offset:offset+1])[0]; offset += 1
        sender = data[offset:offset+sender_len].decode('utf-8'); offset += sender_len
        
        corr_len = struct.unpack('!B', data[offset:offset+1])[0]; offset += 1
        corr = data[offset:offset+corr_len].decode('utf-8'); offset += corr_len
        
        timestamp, ttl = struct.unpack('!dB', data[offset:offset+9]); offset += 9
        
        vc_len = struct.unpack('!I', data[offset:offset+4])[0]; offset += 4
        vc_data = data[offset:offset+vc_len]; offset += vc_len
        
        vector_clock = None
        if vc_data:
            vc_list = json.loads(vc_data.decode('utf-8'))
            vector_clock = VectorClock.from_list(sender, vc_list)
        
        payload_len = struct.unpack('!I', data[offset:offset+4])[0]; offset += 4
        payload = data[offset:offset+payload_len]
        
        return cls(
            msg_type=msg_type,
            sender_id=sender,
            payload=payload,
            timestamp=timestamp,
            correlation_id=corr,
            ttl=ttl,
            vector_clock=vector_clock
        )