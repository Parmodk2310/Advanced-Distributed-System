"""Tests for protocol layer."""

import pytest
import time
from src.protocol.message import Message, MessageType, VectorClock, VectorClockEntry


class TestVectorClock:
    def test_increment(self):
        vc = VectorClock("node-0")
        vc.increment()
        assert vc.clocks["node-0"].counter == 1
        
    def test_merge(self):
        vc1 = VectorClock("node-0")
        vc1.increment()
        
        vc2 = VectorClock("node-1")
        vc2.increment()
        
        vc1.merge(vc2)
        assert "node-1" in vc1.clocks
        assert vc1.clocks["node-0"].counter == 1
        assert vc1.clocks["node-1"].counter == 1
    
    def test_compare_causal(self):
        vc1 = VectorClock("node-0")
        vc1.increment()
        
        vc2 = VectorClock("node-0")
        vc2.increment()
        vc2.increment()
        
        assert vc1.compare(vc2) == "<"
        assert vc2.compare(vc1) == ">"
    
    def test_compare_concurrent(self):
        vc1 = VectorClock("node-0")
        vc1.increment()
        
        vc2 = VectorClock("node-1")
        vc2.increment()
        
        assert vc1.compare(vc2) == "||"


class TestMessage:
    def test_serialize_deserialize(self):
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender_id="node-0",
            payload=b"hello world",
            correlation_id="abc123"
        )
        
        data = msg.serialize()
        restored = Message.deserialize(data)
        
        assert restored.msg_type == MessageType.REQUEST
        assert restored.sender_id == "node-0"
        assert restored.payload == b"hello world"
        assert restored.correlation_id == "abc123"
    
    def test_serialize_with_vector_clock(self):
        vc = VectorClock("node-0")
        vc.increment()
        
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender_id="node-0",
            payload=b"test",
            vector_clock=vc
        )
        
        data = msg.serialize()
        restored = Message.deserialize(data)
        
        assert restored.vector_clock is not None
        assert restored.vector_clock.clocks["node-0"].counter == 1