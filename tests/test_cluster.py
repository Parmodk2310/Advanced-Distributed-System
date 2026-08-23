"""Tests for cluster management."""

import pytest
from src.cluster.consistent_hash import ConsistentHashRing


class TestConsistentHashRing:
    def test_add_node(self):
        ring = ConsistentHashRing(replicas=10)
        ring.add_node("node-0")
        assert "node-0" in ring.nodes
    
    def test_get_node(self):
        ring = ConsistentHashRing(replicas=10)
        ring.add_node("node-0")
        ring.add_node("node-1")
        
        node = ring.get_node("user-123")
        assert node in ["node-0", "node-1"]
    
    def test_remove_node_minimal_remap(self):
        ring = ConsistentHashRing(replicas=10)
        ring.add_node("node-0")
        ring.add_node("node-1")
        ring.add_node("node-2")
        
        # Get mappings for many keys
        mappings_before = {k: ring.get_node(k) for k in [f"key-{i}" for i in range(100)]}
        
        ring.remove_node("node-2")
        
        mappings_after = {k: ring.get_node(k) for k in [f"key-{i}" for i in range(100)]}
        
        # Only keys mapped to node-2 should change
        changes = sum(1 for k in mappings_before if mappings_before[k] != mappings_after[k])
        assert changes < 40  # Should be ~33 with 3 nodes