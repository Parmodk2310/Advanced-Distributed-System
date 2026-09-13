"""SQLite/WAL implementation of the durable state repository."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

from distsys.causal import CausalActor
from distsys.persistence.codec import (
    EncodedCrdtEntry,
    decode_entry,
    decode_version_vector,
    encode_entry,
    encode_version_vector,
)
from distsys.persistence.errors import (
    NodeIdentityMismatchError,
    PersistenceUnavailableError,
    RepositoryIntegrityError,
)
from distsys.persistence.executor import PersistenceExecutor
from distsys.persistence.migrations import apply_migrations, schema_version
from distsys.persistence.models import DurableCausalState, DurableNodeIdentity, RepositoryHealth
from distsys.resilience.deadline import Deadline
from distsys.storage import StoredCrdtEntry


class SQLiteStateRepository:
    """Short-connection SQLite repository safe to call through an async executor."""

    def __init__(
        self,
        path: str | Path,
        executor: PersistenceExecutor,
        *,
        busy_timeout_seconds: float = 5.0,
        synchronous: str = "NORMAL",
    ) -> None:
        if busy_timeout_seconds <= 0:
            raise ValueError("busy_timeout_seconds must be greater than zero")
        synchronous = synchronous.upper()
        if synchronous not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
            raise ValueError("unsupported SQLite synchronous mode")
        self.path = Path(path)
        self.executor = executor
        self.busy_timeout_seconds = busy_timeout_seconds
        self.synchronous = synchronous
        self._opened = False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_seconds,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_seconds * 1000)}")
        return conn

    def _open_sync(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(self._connect()) as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute(f"PRAGMA synchronous = {self.synchronous}")
                apply_migrations(conn)
                result = conn.execute("PRAGMA quick_check").fetchone()
                if result is None or str(result[0]).lower() != "ok":
                    raise RepositoryIntegrityError(f"SQLite quick_check failed: {result}")
        except RepositoryIntegrityError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceUnavailableError(
                f"unable to open SQLite repository: {self.path}"
            ) from exc

    async def open(self) -> None:
        await self.executor.run(self._open_sync)
        self._opened = True

    async def close(self) -> None:
        # Connections are short lived; close is a lifecycle marker.
        self._opened = False

    def _ensure_open(self) -> None:
        if not self._opened:
            raise PersistenceUnavailableError("repository is not open")

    async def integrity_check(self) -> RepositoryHealth:
        self._ensure_open()

        def check() -> RepositoryHealth:
            try:
                with closing(self._connect()) as conn:
                    row = conn.execute("PRAGMA quick_check").fetchone()
                    if row is None or str(row[0]).lower() != "ok":
                        raise RepositoryIntegrityError(f"SQLite quick_check failed: {row}")
                    return RepositoryHealth(True, schema_version(conn), "ok")
            except RepositoryIntegrityError:
                raise
            except sqlite3.Error as exc:
                raise RepositoryIntegrityError("SQLite integrity check failed") from exc

        return await self.executor.run(check)

    @staticmethod
    def _identity_from_row(row: sqlite3.Row) -> DurableNodeIdentity:
        return DurableNodeIdentity(
            node_uuid=uuid.UUID(str(row["node_uuid"])),
            configured_node_id=str(row["configured_node_id"]),
            causal_incarnation=int(row["causal_incarnation"]),
        )

    async def load_identity(self) -> DurableNodeIdentity | None:
        self._ensure_open()

        def load() -> DurableNodeIdentity | None:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    "SELECT node_uuid, configured_node_id, causal_incarnation "
                    "FROM node_identity WHERE singleton_id = 1"
                ).fetchone()
                return None if row is None else self._identity_from_row(row)

        return await self.executor.run(load)

    async def initialize_identity(self, configured_node_id: str) -> DurableNodeIdentity:
        self._ensure_open()
        if not configured_node_id:
            raise ValueError("configured_node_id must not be empty")

        def initialize() -> DurableNodeIdentity:
            now = time.time_ns()
            with closing(self._connect()) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT node_uuid, configured_node_id, causal_incarnation "
                    "FROM node_identity WHERE singleton_id = 1"
                ).fetchone()
                if row is not None:
                    identity = self._identity_from_row(row)
                    if identity.configured_node_id != configured_node_id:
                        raise NodeIdentityMismatchError(
                            "durable database belongs to a different configured node id"
                        )
                    return identity
                identity = DurableNodeIdentity(
                    node_uuid=uuid.uuid4(),
                    configured_node_id=configured_node_id,
                    causal_incarnation=max(1, now),
                )
                conn.execute(
                    "INSERT INTO node_identity("
                    "singleton_id,node_uuid,configured_node_id,causal_incarnation,"
                    "created_at_ns,updated_at_ns"
                    ") VALUES (1,?,?,?,?,?)",
                    (
                        str(identity.node_uuid),
                        identity.configured_node_id,
                        identity.causal_incarnation,
                        now,
                        now,
                    ),
                )
                return identity

        return await self.executor.run(initialize)

    async def load_clock(self) -> DurableCausalState | None:
        self._ensure_open()

        def load() -> DurableCausalState | None:
            with closing(self._connect()) as conn:
                identity_row = conn.execute(
                    "SELECT node_uuid, configured_node_id, causal_incarnation "
                    "FROM node_identity WHERE singleton_id = 1"
                ).fetchone()
                if identity_row is None:
                    return None
                clock_row = conn.execute(
                    "SELECT local_counter, frontier_json FROM causal_clock WHERE singleton_id = 1"
                ).fetchone()
                if clock_row is None:
                    return None
                identity = self._identity_from_row(identity_row)
                actor = CausalActor(identity.configured_node_id, identity.causal_incarnation)
                return DurableCausalState(
                    actor=actor,
                    local_counter=int(clock_row["local_counter"]),
                    frontier=decode_version_vector(str(clock_row["frontier_json"])),
                )

        return await self.executor.run(load)

    @staticmethod
    def _upsert_clock(conn: sqlite3.Connection, state: DurableCausalState, now: int) -> None:
        conn.execute(
            "INSERT INTO causal_clock(singleton_id, local_counter, frontier_json, updated_at_ns) "
            "VALUES (1,?,?,?) "
            "ON CONFLICT(singleton_id) DO UPDATE SET "
            "local_counter=excluded.local_counter, frontier_json=excluded.frontier_json, "
            "updated_at_ns=excluded.updated_at_ns",
            (state.local_counter, encode_version_vector(state.frontier), now),
        )

    async def save_clock(
        self,
        state: DurableCausalState,
        deadline: Deadline | None = None,
    ) -> None:
        self._ensure_open()

        def save() -> None:
            with closing(self._connect()) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                self._upsert_clock(conn, state, time.time_ns())

        await self.executor.run(save, deadline)

    @staticmethod
    def _upsert_entry(
        conn: sqlite3.Connection,
        encoded: EncodedCrdtEntry,
        authoritative: bool,
        now: int,
    ) -> None:
        conn.execute(
            "INSERT INTO crdt_entries("
            "key,crdt_type,state_json,state_version_json,causal_context_json,last_authoritative,updated_at_ns"
            ") VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "crdt_type=excluded.crdt_type,state_json=excluded.state_json,"
            "state_version_json=excluded.state_version_json,"
            "causal_context_json=excluded.causal_context_json,"
            "last_authoritative=excluded.last_authoritative,updated_at_ns=excluded.updated_at_ns",
            (
                encoded.key,
                encoded.crdt_type,
                encoded.state_json,
                encoded.state_version_json,
                encoded.causal_context_json,
                1 if authoritative else 0,
                now,
            ),
        )

    async def load_entries(self) -> tuple[StoredCrdtEntry, ...]:
        self._ensure_open()

        def load() -> tuple[StoredCrdtEntry, ...]:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    "SELECT key, crdt_type, state_json, state_version_json, causal_context_json "
                    "FROM crdt_entries ORDER BY key"
                ).fetchall()
                return tuple(
                    decode_entry(
                        EncodedCrdtEntry(
                            key=str(row["key"]),
                            crdt_type=str(row["crdt_type"]),
                            state_json=str(row["state_json"]),
                            state_version_json=str(row["state_version_json"]),
                            causal_context_json=str(row["causal_context_json"]),
                        )
                    )
                    for row in rows
                )

        return await self.executor.run(load)

    async def _commit_entry_and_clock(
        self,
        entry: StoredCrdtEntry,
        causal_state: DurableCausalState,
        deadline: Deadline | None,
        *,
        authoritative: bool,
    ) -> None:
        self._ensure_open()
        encoded = encode_entry(entry)

        def commit() -> None:
            now = time.time_ns()
            with closing(self._connect()) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                self._upsert_clock(conn, causal_state, now)
                self._upsert_entry(conn, encoded, authoritative, now)

        try:
            await self.executor.run(commit, deadline)
        except PersistenceUnavailableError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceUnavailableError("SQLite commit failed") from exc

    async def commit_mutation(
        self,
        entry: StoredCrdtEntry,
        causal_state: DurableCausalState,
        deadline: Deadline | None = None,
    ) -> None:
        await self._commit_entry_and_clock(entry, causal_state, deadline, authoritative=True)

    async def commit_observed_entry(
        self,
        entry: StoredCrdtEntry,
        causal_state: DurableCausalState,
        deadline: Deadline | None = None,
    ) -> None:
        await self._commit_entry_and_clock(entry, causal_state, deadline, authoritative=True)

    async def mark_authority(self, key: str, authoritative: bool) -> None:
        self._ensure_open()

        def update() -> None:
            with closing(self._connect()) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE crdt_entries SET last_authoritative=?, updated_at_ns=? WHERE key=?",
                    (1 if authoritative else 0, time.time_ns(), key),
                )

        await self.executor.run(update)

    async def backup(self, destination: Path) -> Path:
        from distsys.persistence.backup import backup_sqlite

        self._ensure_open()
        return await self.executor.run(lambda: backup_sqlite(self.path, destination))

    async def schema_version(self) -> int:
        self._ensure_open()
        return await self.executor.run(lambda: self._schema_version_sync())

    def _schema_version_sync(self) -> int:
        with closing(self._connect()) as conn:
            return schema_version(conn)
