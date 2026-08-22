from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from natureai_next.infrastructure.database.migrations import MigrationError
from natureai_next.infrastructure.diagnostics.system_services import (
    SystemClock,
    SystemUuidGenerator,
)
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend


def test_incomplete_existing_library_is_refused_without_mutation(tmp_path: Path) -> None:
    root = tmp_path / "Library"
    backend = SqliteLibraryLifecycleBackend(SystemClock(), SystemUuidGenerator())
    backend.create(root, display_name="Default").close()
    with sqlite3.connect(root / "library.sqlite3") as connection:
        connection.execute("DROP TABLE observations")
    before = (root / "library.sqlite3").read_bytes()
    with pytest.raises(MigrationError, match="schema is incomplete"):
        backend.open(root)
    assert (root / "library.sqlite3").read_bytes() == before
