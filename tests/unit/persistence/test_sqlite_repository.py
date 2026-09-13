import sqlite3
from pathlib import Path

import pytest

from distsys.causal import CausalActor, Dot, VersionVector
from distsys.crdt import CrdtType, GCounter, MVRegister, ORSet, PNCounter
from distsys.persistence.errors import NodeIdentityMismatchError
from distsys.persistence.executor import PersistenceExecutor
from distsys.persistence.models import DurableCausalState
from distsys.persistence.sqlite_repository import SQLiteStateRepository
from distsys.storage import StoredCrdtEntry


def _repo(path: Path) -> SQLiteStateRepository:
    return SQLiteStateRepository(path, PersistenceExecutor(4))


def _entry(key: str, state, kind: CrdtType) -> StoredCrdtEntry:
    actor = CausalActor("node-0", 500)
    return StoredCrdtEntry(
        key=key,
        crdt_type=kind,
        state=state,
        state_version=VersionVector({actor: 1}),
        causal_context=VersionVector({actor: 1}),
    )


@pytest.mark.asyncio
async def test_open_initializes_wal_schema_and_integrity(tmp_path):
    path = tmp_path / "node.db"
    repo = _repo(path)
    await repo.open()
    health = await repo.integrity_check()
    assert health.healthy is True
    assert health.schema_version == 1
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_identity_and_clock_survive_reopen(tmp_path):
    path = tmp_path / "node.db"
    repo = _repo(path)
    await repo.open()
    identity = await repo.initialize_identity("node-0")
    actor = CausalActor("node-0", identity.causal_incarnation)
    causal = DurableCausalState(actor, 7, VersionVector({actor: 7, CausalActor("peer", 9): 4}))
    await repo.save_clock(causal)

    reopened = _repo(path)
    await reopened.open()
    assert await reopened.load_identity() == identity
    assert await reopened.load_clock() == causal


@pytest.mark.asyncio
async def test_identity_mismatch_is_rejected(tmp_path):
    repo = _repo(tmp_path / "node.db")
    await repo.open()
    await repo.initialize_identity("node-0")
    with pytest.raises(NodeIdentityMismatchError):
        await repo.initialize_identity("node-1")


@pytest.mark.asyncio
async def test_commit_mutation_round_trips_all_crdts(tmp_path):
    repo = _repo(tmp_path / "node.db")
    await repo.open()
    identity = await repo.initialize_identity("node-0")
    actor = CausalActor("node-0", identity.causal_incarnation)
    causal = DurableCausalState(actor, 4, VersionVector({actor: 4}))
    dot1 = Dot(actor, 1)
    dot2 = Dot(actor, 2)
    entries = [
        _entry("g", GCounter({actor: 3}), CrdtType.GCOUNTER),
        _entry("pn", PNCounter(GCounter({actor: 5}), GCounter({actor: 2})), CrdtType.PNCOUNTER),
        _entry("set", ORSet({"x": {dot1, dot2}}, {dot1}), CrdtType.ORSET),
        _entry("reg", MVRegister({dot1: '"x"', dot2: '"y"'}, {dot1}), CrdtType.MVREGISTER),
    ]
    for entry in entries:
        await repo.commit_mutation(entry, causal)

    reopened = _repo(tmp_path / "node.db")
    await reopened.open()
    assert set(await reopened.load_entries()) == set(entries)
    assert await reopened.load_clock() == causal


@pytest.mark.asyncio
async def test_mark_authority_updates_persisted_flag(tmp_path):
    path = tmp_path / "node.db"
    repo = _repo(path)
    await repo.open()
    identity = await repo.initialize_identity("node-0")
    actor = CausalActor("node-0", identity.causal_incarnation)
    causal = DurableCausalState(actor, 1, VersionVector({actor: 1}))
    await repo.commit_mutation(_entry("g", GCounter({actor: 1}), CrdtType.GCOUNTER), causal)
    await repo.mark_authority("g", False)
    with sqlite3.connect(path) as conn:
        assert (
            conn.execute("SELECT last_authoritative FROM crdt_entries WHERE key='g'").fetchone()[0]
            == 0
        )


class TrackingConnection(sqlite3.Connection):
    close_calls = 0

    def close(self) -> None:
        type(self).close_calls += 1
        super().close()


@pytest.mark.asyncio
async def test_repository_closes_short_lived_sqlite_connections(tmp_path, monkeypatch):
    path = tmp_path / "node.db"
    repo = _repo(path)
    TrackingConnection.close_calls = 0

    def tracked_connect():
        conn = sqlite3.connect(
            path,
            timeout=repo.busy_timeout_seconds,
            isolation_level=None,
            factory=TrackingConnection,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {int(repo.busy_timeout_seconds * 1000)}")
        return conn

    monkeypatch.setattr(repo, "_connect", tracked_connect)
    await repo.open()
    await repo.integrity_check()
    await repo.initialize_identity("node-0")

    assert TrackingConnection.close_calls >= 3
