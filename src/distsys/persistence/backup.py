"""Safe SQLite backup helper."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def backup_sqlite(source_path: Path, destination_path: Path) -> Path:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_path) as source, sqlite3.connect(destination_path) as target:
        source.backup(target)
    return destination_path
