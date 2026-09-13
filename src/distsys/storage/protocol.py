"""Storage protocol shared by in-memory and durable CRDT stores."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from distsys.causal import VersionVector
from distsys.crdt import CrdtType
from distsys.storage.models import StoredCrdtEntry


class CrdtStateStore(Protocol):
    def key_lock(self, key: str) -> AbstractAsyncContextManager[None]: ...

    async def get(self, key: str) -> StoredCrdtEntry | None: ...

    async def snapshot(self, key: str) -> StoredCrdtEntry | None: ...

    async def replace(
        self, entry: StoredCrdtEntry, expected_type: CrdtType | None = None
    ) -> StoredCrdtEntry: ...

    async def merge_entry(self, incoming: StoredCrdtEntry) -> StoredCrdtEntry: ...

    async def merge_metadata(
        self, key: str, causal_context: VersionVector
    ) -> StoredCrdtEntry | None: ...

    async def keys(self) -> tuple[str, ...]: ...

    async def snapshot_all(self, limit: int | None = None) -> tuple[StoredCrdtEntry, ...]: ...
