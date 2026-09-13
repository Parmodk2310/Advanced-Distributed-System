import sqlite3

import pytest

from distsys.persistence.errors import RepositorySchemaError
from distsys.persistence.migrations import CURRENT_SCHEMA_VERSION, apply_migrations, schema_version


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def test_apply_migrations_initializes_schema_v1():
    conn = sqlite3.connect(":memory:")
    assert apply_migrations(conn) == 1
    assert schema_version(conn) == CURRENT_SCHEMA_VERSION == 1
    assert {
        "schema_migrations",
        "node_identity",
        "causal_clock",
        "crdt_entries",
    }.issubset(_tables(conn))


def test_apply_migrations_is_idempotent():
    conn = sqlite3.connect(":memory:")
    apply_migrations(conn)
    apply_migrations(conn)
    assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1


def test_newer_schema_is_rejected():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at_ns INTEGER NOT NULL)"
    )
    conn.execute("INSERT INTO schema_migrations(version, applied_at_ns) VALUES (99, 1)")
    conn.commit()
    with pytest.raises(RepositorySchemaError):
        apply_migrations(conn)
