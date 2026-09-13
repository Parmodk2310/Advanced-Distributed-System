import pytest

from distsys.causal import CausalActor, Dot, VersionVector
from distsys.crdt import CrdtType, GCounter, MVRegister, ORSet, PNCounter
from distsys.persistence.codec import decode_entry, encode_entry, encode_version_vector
from distsys.storage import StoredCrdtEntry


def _entry(state, crdt_type):
    a = CausalActor("node-a", 1)
    b = CausalActor("node-b", 2)
    return StoredCrdtEntry(
        key="k",
        crdt_type=crdt_type,
        state=state,
        state_version=VersionVector({a: 2, b: 1}),
        causal_context=VersionVector({a: 2, b: 3}),
    )


def test_version_vector_encoding_is_canonical():
    a = CausalActor("node-b", 2)
    b = CausalActor("node-a", 1)
    assert encode_version_vector(VersionVector({a: 4, b: 7})) == encode_version_vector(
        VersionVector({b: 7, a: 4})
    )


@pytest.mark.parametrize(
    ("state", "crdt_type"),
    [
        (GCounter({CausalActor("node-a", 1): 4}), CrdtType.GCOUNTER),
        (
            PNCounter(
                GCounter({CausalActor("node-a", 1): 7}),
                GCounter({CausalActor("node-b", 2): 2}),
            ),
            CrdtType.PNCOUNTER,
        ),
        (
            ORSet(
                {"x": {Dot(CausalActor("node-a", 1), 1)}},
                {Dot(CausalActor("node-a", 1), 1)},
            ),
            CrdtType.ORSET,
        ),
        (
            MVRegister(
                {
                    Dot(CausalActor("node-a", 1), 1): '"a"',
                    Dot(CausalActor("node-b", 2), 1): '"b"',
                },
                {Dot(CausalActor("node-a", 1), 1)},
            ),
            CrdtType.MVREGISTER,
        ),
    ],
)
def test_entry_round_trip(state, crdt_type):
    original = _entry(state, crdt_type)
    assert decode_entry(encode_entry(original)) == original
