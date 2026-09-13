import pytest

from distsys.causal import CausalActor, Dot
from distsys.crdt import ORSet


def test_remove_observed_add():
    a = CausalActor("node-0", 1)
    state = ORSet().add("python", Dot(a, 1)).remove("python")
    assert "python" not in state.value()


def test_unseen_concurrent_add_survives_remove():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    base = ORSet().add("python", Dot(a, 1))
    removed = base.remove("python")
    concurrent = base.add("python", Dot(b, 1))
    merged = removed.merge(concurrent)
    assert merged.value() == frozenset({"python"})
    assert merged == concurrent.merge(removed)
    assert merged.merge(merged) == merged


def test_orset_requires_string_elements():
    a = CausalActor("node-0", 1)
    with pytest.raises(TypeError):
        ORSet().add(123, Dot(a, 1))  # type: ignore[arg-type]
