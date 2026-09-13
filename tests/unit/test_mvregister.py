import pytest

from distsys.causal import CausalActor, Dot
from distsys.crdt import MVRegister


def test_concurrent_values_survive_merge():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    left = MVRegister().write("medium", Dot(a, 1))
    right = MVRegister().write("high", Dot(b, 1))
    merged = left.merge(right)
    assert set(merged.values()) == {"medium", "high"}
    assert merged == right.merge(left)
    assert merged.merge(merged) == merged


def test_later_write_supersedes_all_visible_values():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    c = CausalActor("node-2", 1)
    concurrent = (
        MVRegister().write("medium", Dot(a, 1)).merge(MVRegister().write("high", Dot(b, 1)))
    )
    resolved = concurrent.write("medium-high", Dot(c, 1))
    assert resolved.values() == ("medium-high",)


def test_register_rejects_non_json_value():
    a = CausalActor("node-0", 1)
    with pytest.raises((TypeError, ValueError)):
        MVRegister().write({1, 2}, Dot(a, 1))
