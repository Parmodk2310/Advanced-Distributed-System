import pytest

from distsys.causal import CausalActor, VersionVector
from distsys.crdt import CrdtType, GCounter
from distsys.persistence.executor import PersistenceExecutor
from distsys.persistence.models import DurableCausalState
from distsys.persistence.sqlite_repository import SQLiteStateRepository
from distsys.recovery.restore import RestoreService
from distsys.storage import StoredCrdtEntry


@pytest.mark.asyncio
async def test_restore_initializes_fresh_identity_clock_and_empty_store(tmp_path):
    repo = SQLiteStateRepository(tmp_path / "node.db", PersistenceExecutor(4))
    await repo.open()
    restored = await RestoreService(repo, "node-0").restore()
    assert restored.identity.configured_node_id == "node-0"
    assert restored.causal_state.local_counter == 0
    assert await restored.memory_store.keys() == ()


@pytest.mark.asyncio
async def test_restore_merges_entry_context_into_durable_frontier(tmp_path):
    repo = SQLiteStateRepository(tmp_path / "node.db", PersistenceExecutor(4))
    await repo.open()
    identity = await repo.initialize_identity("node-0")
    actor = CausalActor("node-0", identity.causal_incarnation)
    remote = CausalActor("node-1", 77)
    causal = DurableCausalState(actor, 1, VersionVector({actor: 1}))
    entry = StoredCrdtEntry(
        "k",
        CrdtType.GCOUNTER,
        GCounter({actor: 1}),
        VersionVector({actor: 1}),
        VersionVector({actor: 1, remote: 5}),
    )
    await repo.commit_mutation(entry, causal)
    restored = await RestoreService(repo, "node-0").restore()
    assert restored.causal_state.frontier.get(remote) == 5
    assert await restored.memory_store.get("k") == entry
