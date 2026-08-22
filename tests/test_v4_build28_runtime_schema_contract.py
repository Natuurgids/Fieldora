from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from natureai_next.application.library_service import LibraryService
from natureai_next.infrastructure.database.migrations import MigrationError
from natureai_next.infrastructure.diagnostics.system_services import (
    SystemClock,
    SystemUuidGenerator,
)
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend


def service():
    return LibraryService(
        SystemClock(),
        SystemUuidGenerator(),
        backend_factory=lambda c, i, s: SqliteLibraryLifecycleBackend(c, i, s),
    )


def test_clean_creation_has_repository_schema(tmp_path: Path) -> None:
    with service().open_or_create_clean(tmp_path / "Library") as opened:
        with opened.connection_factory.connect(read_only=True) as con:
            assert con.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


def test_existing_schema_drift_is_refused_not_reconstructed(tmp_path: Path) -> None:
    root = tmp_path / "Library"
    service().open_or_create_clean(root).close()
    with sqlite3.connect(root / "library.sqlite3") as con:
        con.execute("DROP TABLE observations")
    with pytest.raises(MigrationError):
        service().open(root)
