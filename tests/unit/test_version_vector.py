from distsys.causal import CausalActor, Dot
from distsys.causal.version_vector import VersionRelation, VersionVector


def test_partial_order_before_after_equal_concurrent():
    a0 = CausalActor("node-0", 1)
    a1 = CausalActor("node-1", 1)
    before = VersionVector({a0: 3, a1: 2})
    after = VersionVector({a0: 4, a1: 2})
    concurrent = VersionVector({a0: 3, a1: 3})
    assert before.compare(after) is VersionRelation.BEFORE
    assert after.compare(before) is VersionRelation.AFTER
    assert after.compare(after) is VersionRelation.EQUAL
    assert after.compare(concurrent) is VersionRelation.CONCURRENT


def test_merge_is_pointwise_max_commutative_associative_idempotent():
    a0 = CausalActor("node-0", 1)
    a1 = CausalActor("node-1", 1)
    a = VersionVector({a0: 5, a1: 2})
    b = VersionVector({a0: 3, a1: 4})
    c = VersionVector({a0: 8, a1: 1})
    assert a.merge(b) == VersionVector({a0: 5, a1: 4})
    assert a.merge(b) == b.merge(a)
    assert a.merge(b).merge(c) == a.merge(b.merge(c))
    assert a.merge(a) == a


def test_missing_frontier_reports_counter_range():
    a0 = CausalActor("node-0", 1)
    local = VersionVector({a0: 6})
    required = VersionVector({a0: 8})
    assert local.missing_from(required) == {a0: (7, 8)}


def test_with_dot_keeps_highest_counter():
    a0 = CausalActor("node-0", 1)
    vector = VersionVector().with_dot(Dot(a0, 3)).with_dot(Dot(a0, 2))
    assert vector.get(a0) == 3


def test_dominance_includes_equality_and_concurrent_does_not_dominate():
    a0 = CausalActor("node-0", 1)
    a1 = CausalActor("node-1", 1)
    a = VersionVector({a0: 4, a1: 2})
    b = VersionVector({a0: 3, a1: 2})
    c = VersionVector({a0: 3, a1: 3})
    assert a.dominates(a)
    assert a.dominates(b)
    assert not a.dominates(c)
    assert a.concurrent_with(c)
