from __future__ import annotations

import sqlite3
from datetime import UTC
from pathlib import Path

import pytest

from natureai_next.infrastructure.database.migrations import MigrationError
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend


class Clock:
    def now_utc(self):
        from datetime import datetime

        return datetime(2026, 1, 1, tzinfo=UTC)


class Ids:
    def __init__(self):
        self.n = 0

    def new_uuid(self):
        self.n += 1
        return f"00000000-0000-0000-0000-{self.n:012d}"


def test_runtime_validation_never_repairs_schema(tmp_path: Path) -> None:
    backend = SqliteLibraryLifecycleBackend(Clock(), Ids())
    opened = backend.create(tmp_path / "library", display_name="Test")
    try:
        with sqlite3.connect(opened.layout.database) as con:
            con.execute("DROP TABLE observations")
        with pytest.raises(MigrationError, match="schema is incomplete"):
            opened.ensure_runtime_schema()
        assert not list(opened.layout.backups.glob("incomplete-schema-*"))
    finally:
        opened.close()


def test_runtime_validation_never_repairs_identity(tmp_path: Path) -> None:
    backend = SqliteLibraryLifecycleBackend(Clock(), Ids())
    opened = backend.create(tmp_path / "library", display_name="Test")
    try:
        with sqlite3.connect(opened.layout.database) as con:
            con.execute("UPDATE library_info SET public_id='stale' WHERE id=1")
        with pytest.raises(MigrationError, match="identity differ"):
            opened.ensure_runtime_schema()
    finally:
        opened.close()


def test_close_releases_lock_without_repair(tmp_path: Path) -> None:
    backend = SqliteLibraryLifecycleBackend(Clock(), Ids())
    root = tmp_path / "library"
    opened = backend.create(root, display_name="Test")
    opened.close()
    reopened = backend.open(root)
    reopened.close()
