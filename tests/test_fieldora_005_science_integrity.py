import json
import sqlite3
from pathlib import Path

from natureai_next.application.backup import LibraryBackupService
from natureai_next.application.recovery import LibraryRecoveryService
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry
from natureai_next.infrastructure.subsystems.science import (
    SCIENCE_SUBSYSTEM_KEY,
    science_descriptor,
)


def test_science_is_registered_and_integrity_checked(tmp_path: Path) -> None:
    database = tmp_path / "science.sqlite3"
    registry = SubsystemDatabaseRegistry(
        (science_descriptor(database),), "0.05.0"
    )
    registry.activate(SCIENCE_SUBSYSTEM_KEY)
    status = registry.status(SCIENCE_SUBSYSTEM_KEY, run_integrity_check=True)
    assert status.schema_version == 2
    assert not status.message


def test_verified_backup_includes_science_database(tmp_path: Path) -> None:
    catalog = tmp_path / "library.sqlite3"
    science = tmp_path / "science.sqlite3"
    for path, table in ((catalog, "assets"), (science, "science_projects")):
        with sqlite3.connect(path) as connection:
            connection.execute(f"CREATE TABLE {table}(id TEXT PRIMARY KEY)")

    def backup_catalog(destination: Path) -> Path:
        with sqlite3.connect(catalog) as source, sqlite3.connect(destination) as target:
            source.backup(target)
        return destination

    result = LibraryBackupService(
        backup_catalog,
        library_name="Fieldora Test",
        additional_databases={"science": science},
    ).create(tmp_path / "backup.sqlite3")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    copied = result.database_path.with_suffix(result.database_path.suffix + ".files")
    assert result.subsystem_databases_copied == 1
    assert manifest["subsystem_databases"][0]["key"] == "science"
    with sqlite3.connect(copied / "databases" / "science.sqlite3") as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    verified = LibraryRecoveryService().verify(result.database_path)
    assert verified.subsystem_databases[0]["key"] == "science"
