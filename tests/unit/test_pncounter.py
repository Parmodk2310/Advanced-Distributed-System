from distsys.causal import CausalActor
from distsys.crdt import PNCounter


def test_pncounter_increment_decrement_and_merge_laws():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    left = PNCounter().increment(a, 5).decrement(a, 1)
    right = PNCounter().increment(b, 4).decrement(b, 2)
    third = PNCounter().increment(a, 2).decrement(b, 1)
    merged = left.merge(right)
    assert merged.value() == 6
    assert merged == right.merge(left)
    assert left.merge(right).merge(third) == left.merge(right.merge(third))
    assert left.merge(left) == left
