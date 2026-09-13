from uuid import UUID

import pytest

from distsys.causal import CausalActor, VersionVector
from distsys.persistence.models import DurableCausalState, DurableNodeIdentity


def test_durable_identity_rejects_empty_node_id():
    with pytest.raises(ValueError):
        DurableNodeIdentity(
            node_uuid=UUID("00000000-0000-0000-0000-000000000001"),
            configured_node_id="",
            causal_incarnation=1,
        )


def test_durable_identity_rejects_non_positive_causal_incarnation():
    with pytest.raises(ValueError):
        DurableNodeIdentity(
            node_uuid=UUID("00000000-0000-0000-0000-000000000001"),
            configured_node_id="node-0",
            causal_incarnation=0,
        )


def test_durable_causal_state_counter_matches_actor_component():
    actor = CausalActor("node-0", 500)
    state = DurableCausalState(actor, 8, VersionVector({actor: 8}))
    assert state.frontier.get(actor) == state.local_counter


def test_durable_causal_state_rejects_frontier_ahead_of_local_counter():
    actor = CausalActor("node-0", 500)
    with pytest.raises(ValueError):
        DurableCausalState(actor, 8, VersionVector({actor: 9}))
