"""Consistent SQLite online backups and integrity verification."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


def create_database_backup(factory: SqliteConnectionFactory, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".tmp")
    temp.unlink(missing_ok=True)
    source = factory.connect(read_only=True)
    target = sqlite3.connect(temp)
    try:
        source.backup(target)
        target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        target.close()
        source.close()
    check = sqlite3.connect(temp)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"backup integrity check failed: {result}")
    finally:
        check.close()
    temp.replace(destination)
    return destination
