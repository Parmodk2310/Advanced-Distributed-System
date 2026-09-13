"""SQLite schema migrations for durable Phase-5 state."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable

from distsys.persistence.errors import RepositorySchemaError

CURRENT_SCHEMA_VERSION = 1


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def schema_version(conn: sqlite3.Connection) -> int:
    if not _has_table(conn, "schema_migrations"):
        return 0
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0] or 0)


def _migration_v1(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at_ns INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS node_identity (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            node_uuid TEXT NOT NULL UNIQUE,
            configured_node_id TEXT NOT NULL,
            causal_incarnation INTEGER NOT NULL,
            created_at_ns INTEGER NOT NULL,
            updated_at_ns INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS causal_clock (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            local_counter INTEGER NOT NULL,
            frontier_json TEXT NOT NULL,
            updated_at_ns INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crdt_entries (
            key TEXT PRIMARY KEY,
            crdt_type TEXT NOT NULL,
            state_json TEXT NOT NULL,
            state_version_json TEXT NOT NULL,
            causal_context_json TEXT NOT NULL,
            last_authoritative INTEGER NOT NULL CHECK (last_authoritative IN (0, 1)),
            updated_at_ns INTEGER NOT NULL
        );
        """)


_MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {1: _migration_v1}


def apply_migrations(conn: sqlite3.Connection) -> int:
    current = schema_version(conn)
    if current > CURRENT_SCHEMA_VERSION:
        raise RepositorySchemaError(
            f"database schema {current} is newer than supported {CURRENT_SCHEMA_VERSION}"
        )
    for version in range(current + 1, CURRENT_SCHEMA_VERSION + 1):
        migration = _MIGRATIONS[version]
        try:
            conn.execute("BEGIN")
            migration(conn)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at_ns) VALUES (?, ?)",
                (version, time.time_ns()),
            )
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            raise RepositorySchemaError(f"failed to apply schema migration {version}") from exc
    return schema_version(conn)
