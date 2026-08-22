from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from natureai_next.infrastructure.database.migrations.core import Migration
from natureai_next.infrastructure.subsystems.registry import (
    SubsystemDatabaseDescriptor,
    SubsystemDatabaseRegistry,
)


def test_incompatible_clean_start_subsystem_is_archived_and_recreated(tmp_path: Path) -> None:
    database = tmp_path / "subsystems" / "enrichment.sqlite3"
    database.parent.mkdir(parents=True)
    old = Migration(1, "old", "CREATE TABLE old_record(id INTEGER PRIMARY KEY);")
    new = Migration(1, "new", "CREATE TABLE new_record(id INTEGER PRIMARY KEY);")

    first = SubsystemDatabaseRegistry(
        (SubsystemDatabaseDescriptor("enrichment", database, (old,), optional=False),),
        "4.0.0.dev1",
    )
    first.activate("enrichment")

    second = SubsystemDatabaseRegistry(
        (SubsystemDatabaseDescriptor("enrichment", database, (new,), optional=False),),
        "4.0.0.dev1",
    )
    second.activate("enrichment")

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='new_record'"
        ).fetchone()
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='old_record'"
            ).fetchone()
            is None
        )

    archives = tuple(database.parent.glob("enrichment.sqlite3.incompatible-*"))
    preserved_databases = tuple(path for path in archives if not path.name.endswith(".json"))
    reports = tuple(path for path in archives if path.name.endswith(".json"))
    assert len(preserved_databases) == 1
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert "checksum mismatch for migration 1" in report["reason"]
    with sqlite3.connect(preserved_databases[0]) as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='old_record'"
        ).fetchone()


def test_windows_debug_launcher_captures_native_stderr_verbatim() -> None:
    installer = Path("scripts/install_windows.ps1").read_text(encoding="utf-8")
    assert "-RedirectStandardError $stderrLog" in installer
    assert "=== STANDARD ERROR ===" in installer
    assert "2>&1 |" not in installer
