from distsys.causal import CausalActor, VersionVector
from distsys.causal.token import CausalToken


def test_empty_token_has_empty_vector():
    assert CausalToken.empty().version == VersionVector()


def test_token_merge_combines_session_knowledge():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    left = CausalToken(VersionVector({a: 2}))
    right = CausalToken(VersionVector({b: 4}))
    assert left.merge(right).version == VersionVector({a: 2, b: 4})
