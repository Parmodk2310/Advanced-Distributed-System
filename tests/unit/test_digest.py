import pytest

from distsys.causal import CausalActor, VersionVector
from distsys.crdt import CrdtType
from distsys.replication.digest import CrdtDigestEntry, DigestRelation, compare_digest


def digest(key: str, sv: VersionVector, cc: VersionVector | None = None) -> CrdtDigestEntry:
    return CrdtDigestEntry(key, CrdtType.GCOUNTER, sv, cc or sv)


def test_digest_relations():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    equal = VersionVector({a: 2})
    assert compare_digest(digest("k", equal), digest("k", equal)) is DigestRelation.EQUAL
    assert (
        compare_digest(digest("k", VersionVector({a: 3})), digest("k", VersionVector({a: 2})))
        is DigestRelation.LOCAL_AHEAD
    )
    assert (
        compare_digest(digest("k", VersionVector({a: 2})), digest("k", VersionVector({a: 3})))
        is DigestRelation.REMOTE_AHEAD
    )
    assert (
        compare_digest(
            digest("k", VersionVector({a: 3, b: 1})),
            digest("k", VersionVector({a: 2, b: 2})),
        )
        is DigestRelation.CONCURRENT
    )


def test_equal_state_but_different_causal_context_is_metadata_only():
    a = CausalActor("node-0", 1)
    b = CausalActor("node-1", 1)
    state = VersionVector({a: 2})
    local = digest("k", state, VersionVector({a: 2, b: 1}))
    remote = digest("k", state, VersionVector({a: 2, b: 3}))
    assert compare_digest(local, remote) is DigestRelation.METADATA_ONLY


def test_digest_rejects_key_or_type_mismatch():
    a = CausalActor("node-0", 1)
    vv = VersionVector({a: 1})
    with pytest.raises(ValueError):
        compare_digest(digest("a", vv), digest("b", vv))
    with pytest.raises(ValueError):
        compare_digest(
            digest("a", vv),
            CrdtDigestEntry("a", CrdtType.ORSET, vv, vv),
        )
