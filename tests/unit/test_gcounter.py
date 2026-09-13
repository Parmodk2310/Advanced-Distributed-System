import pytest

from distsys.causal import CausalActor
from distsys.crdt import CrdtType, GCounter


def test_crdt_type_values_are_stable():
    assert CrdtType.GCOUNTER.value == "gcounter"
    assert CrdtType.PNCOUNTER.value == "pncounter"
    assert CrdtType.ORSET.value == "orset"
    assert CrdtType.MVREGISTER.value == "mvregister"


def test_gcounter_increment_value_and_merge_laws():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    left = GCounter().increment(a, 5).increment(b, 2)
    right = GCounter().increment(a, 3).increment(b, 4)
    third = GCounter().increment(a, 8)
    merged = left.merge(right)
    assert merged.value() == 9
    assert merged == right.merge(left)
    assert left.merge(right).merge(third) == left.merge(right.merge(third))
    assert left.merge(left) == left


def test_gcounter_rejects_non_positive_increment():
    a = CausalActor("node-0", 1)
    with pytest.raises(ValueError):
        GCounter().increment(a, 0)
