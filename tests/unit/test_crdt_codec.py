from distsys.causal import CausalActor, CausalToken, Dot, VersionVector
from distsys.crdt import CrdtType, GCounter, MVRegister, ORSet, PNCounter
from distsys.replication.codec import (
    actor_from_proto,
    actor_to_proto,
    digest_from_proto,
    digest_to_proto,
    state_from_proto,
    state_to_proto,
    token_from_proto,
    token_to_proto,
    version_from_proto,
    version_to_proto,
)
from distsys.replication.digest import CrdtDigestEntry
from distsys.storage import StoredCrdtEntry


def vv(actor, counter):
    return VersionVector({actor: counter})


def test_causal_primitives_round_trip():
    actor = CausalActor("node-0", 123)
    vector = VersionVector({actor: 7})
    token = CausalToken(vector)
    assert actor_from_proto(actor_to_proto(actor)) == actor
    assert version_from_proto(version_to_proto(vector)) == vector
    assert token_from_proto(token_to_proto(token)) == token


def test_gcounter_state_round_trip():
    actor = CausalActor("node-0", 1)
    vector = vv(actor, 2)
    entry = StoredCrdtEntry(
        "views", CrdtType.GCOUNTER, GCounter().increment(actor, 5), vector, vector
    )
    assert state_from_proto(state_to_proto(entry)) == entry


def test_pncounter_state_round_trip():
    actor = CausalActor("node-0", 1)
    vector = vv(actor, 2)
    state = PNCounter().increment(actor, 5).decrement(actor, 2)
    entry = StoredCrdtEntry("balance", CrdtType.PNCOUNTER, state, vector, vector)
    assert state_from_proto(state_to_proto(entry)) == entry


def test_orset_state_round_trip():
    actor = CausalActor("node-0", 1)
    dot = Dot(actor, 1)
    vector = vv(actor, 1)
    state = ORSet().add("python", dot).add("rust", Dot(actor, 2)).remove("python")
    entry = StoredCrdtEntry("tags", CrdtType.ORSET, state, vector, vector)
    assert state_from_proto(state_to_proto(entry)) == entry


def test_mvregister_state_round_trip_is_deterministic():
    actor = CausalActor("node-0", 1)
    dot = Dot(actor, 1)
    vector = vv(actor, 1)
    state = MVRegister().write({"b": 2, "a": 1}, dot)
    entry = StoredCrdtEntry("status", CrdtType.MVREGISTER, state, vector, vector)
    encoded1 = state_to_proto(entry).SerializeToString(deterministic=True)
    encoded2 = state_to_proto(entry).SerializeToString(deterministic=True)
    assert encoded1 == encoded2
    assert state_from_proto(state_to_proto(entry)) == entry


def test_digest_round_trip():
    actor = CausalActor("node-0", 1)
    digest = CrdtDigestEntry("k", CrdtType.GCOUNTER, vv(actor, 1), vv(actor, 2))
    assert digest_from_proto(digest_to_proto(digest)) == digest
