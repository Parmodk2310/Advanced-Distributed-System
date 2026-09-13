import pytest

from distsys.causal.actor import CausalActor


def test_actor_identity_includes_incarnation():
    assert CausalActor("node-1", 10) != CausalActor("node-1", 11)


def test_actor_wire_key():
    assert CausalActor("node-1", 10).wire_key() == "node-1@10"


def test_actor_validation():
    with pytest.raises(ValueError):
        CausalActor("", 1)
    with pytest.raises(ValueError):
        CausalActor("node-1", -1)
