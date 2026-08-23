"""Tests for CRDT implementations."""

import pytest
from src.consistency.crdt.g_counter import GCounter
from src.consistency.crdt.pn_counter import PNCounter
from src.consistency.crdt.lww_register import LWWRegister
from src.consistency.crdt.or_set import ORSet


class TestGCounter:
    def test_increment(self):
        gc = GCounter("views", "node-0")
        gc.increment(5)
        assert gc.value() == 5
    
    def test_merge(self):
        gc1 = GCounter("views", "node-0")
        gc1.increment(10)
        
        gc2 = GCounter("views", "node-1")
        gc2.increment(20)
        
        gc1.merge(gc2)
        assert gc1.value() == 30
    
    def test_idempotency(self):
        gc = GCounter("views", "node-0")
        gc.increment(5)
        gc.merge(GCounter("views", "node-0"))
        assert gc.value() == 5


class TestPNCounter:
    def test_increment_decrement(self):
        pnc = PNCounter("balance", "node-0")
        pnc.increment(100)
        pnc.decrement(30)
        assert pnc.value() == 70
    
    def test_merge(self):
        pnc1 = PNCounter("balance", "node-0")
        pnc1.increment(100)
        
        pnc2 = PNCounter("balance", "node-1")
        pnc2.decrement(50)
        
        pnc1.merge(pnc2)
        assert pnc1.value() == 50


class TestLWWRegister:
    def test_set_get(self):
        reg = LWWRegister("config", "node-0")
        reg.set("value1")
        assert reg.get() == "value1"
    
    def test_merge(self):
        import time
        reg1 = LWWRegister("config", "node-0")
        reg1.set("old")
        
        time.sleep(0.01)
        
        reg2 = LWWRegister("config", "node-1")
        reg2.set("new")
        
        reg1.merge(reg2)
        assert reg1.get() == "new"


class TestORSet:
    def test_add_remove(self):
        s = ORSet("cart", "node-0")
        s.add("item1")
        assert s.contains("item1")
        
        s.remove("item1")
        assert not s.contains("item1")
    
    def test_merge(self):
        s1 = ORSet("cart", "node-0")
        s1.add("item1")
        
        s2 = ORSet("cart", "node-1")
        s2.add("item2")
        
        s1.merge(s2)
        assert s1.contains("item1")
        assert s1.contains("item2")