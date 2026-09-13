import pytest

from distsys.causal.actor import CausalActor
from distsys.causal.dot import Dot


def test_dot_uses_actor_and_counter():
    actor = CausalActor("node-1", 10)
    assert Dot(actor, 1).counter == 1


def test_dot_validation():
    actor = CausalActor("node-1", 10)
    with pytest.raises(ValueError):
        Dot(actor, 0)
