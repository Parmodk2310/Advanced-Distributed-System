import pytest

from distsys.causal import CausalActor, VersionVector
from distsys.crdt import CrdtType, GCounter
from distsys.persistence.executor import PersistenceExecutor
from distsys.persistence.models import DurableCausalState
from distsys.persistence.sqlite_repository import SQLiteStateRepository
from distsys.storage import StoredCrdtEntry


@pytest.mark.asyncio
async def test_live_database_backup_restores_committed_state(tmp_path):
    source = SQLiteStateRepository(tmp_path / "node.db", PersistenceExecutor(2))
    await source.open()
    identity = await source.initialize_identity("node-0")
    actor = CausalActor("node-0", identity.causal_incarnation)
    causal = DurableCausalState(actor, 1, VersionVector({actor: 1}))
    entry = StoredCrdtEntry(
        "k",
        CrdtType.GCOUNTER,
        GCounter({actor: 3}),
        VersionVector({actor: 1}),
        VersionVector({actor: 1}),
    )
    await source.commit_mutation(entry, causal)

    backup_path = await source.backup(tmp_path / "backup.db")
    restored = SQLiteStateRepository(backup_path, PersistenceExecutor(2))
    await restored.open()
    assert await restored.load_entries() == (entry,)
