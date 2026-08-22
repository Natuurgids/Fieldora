import sqlite3
from pathlib import Path

import pytest

from natureai_next.domain.library import LibraryLayout, LibraryManifest
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import (
    CORE_MIGRATIONS,
    MigrationError,
    MigrationRunner,
)
from natureai_next.infrastructure.diagnostics.system_services import SystemClock, SystemUuidGenerator
from natureai_next.infrastructure.filesystem.library_manifest import write_manifest
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend


def test_phase_d_library_is_backed_up_and_explicitly_upgraded(tmp_path: Path) -> None:
    root = tmp_path / "FieldoraLibrary"
    layout = LibraryLayout.at(root)
    layout.create_directories()
    public_id = "library-1"
    write_manifest(
        layout.manifest,
        LibraryManifest(1, public_id, "Fieldora Test", 1),
    )
    factory = SqliteConnectionFactory(layout.database)
    with factory.connect() as connection:
        MigrationRunner(CORE_MIGRATIONS[:30], "0.08.34").apply(connection)
        connection.execute(
            "INSERT INTO library_info(id,public_id,created_at_us,current_schema_version,"
            "minimum_app_version,display_name,default_locale) VALUES(1,?,?,?,?,?,?)",
            (public_id, 1, 30, "0.08.34", "Fieldora Test", "en"),
        )
        connection.commit()

    backend = SqliteLibraryLifecycleBackend(SystemClock(), SystemUuidGenerator())
    with pytest.raises(MigrationError, match="explicit schema upgrade"):
        backend.open(root)
    opened = backend.upgrade(root)
    try:
        with opened.connection_factory.connect(read_only=True) as connection:
            count = connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
            version = connection.execute(
                "SELECT current_schema_version FROM library_info WHERE id=1"
            ).fetchone()[0]
        assert count == len(CORE_MIGRATIONS)
        assert version == len(CORE_MIGRATIONS)
        backups = tuple(layout.backups.glob("pre-schema-30-to-*.sqlite3"))
        assert len(backups) == 1
        with sqlite3.connect(backups[0]) as backup:
            assert backup.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 30
    finally:
        opened.close()


def test_launcher_error_copy_is_fieldora() -> None:
    source = (
        Path(__file__).parents[1] / "src/natureai_next/bootstrap/aperture_launcher.py"
    ).read_text(encoding="utf-8")
    assert '"Fieldora could not start.' in source
    assert '"Use Fieldora (Debug)' in source
    assert 'MessageBoxW(0, message, "Fieldora"' in source


def test_uninstall_removes_current_and_legacy_links() -> None:
    root = Path(__file__).parents[1]
    windows = (root / "scripts/uninstall_windows.ps1").read_text(encoding="utf-8")
    linux = (root / "scripts/uninstall_linux.sh").read_text(encoding="utf-8")
    for name in (
        "Fieldora.lnk",
        "Fieldora (Debug).lnk",
        "Fieldora - Select Library.lnk",
        "Fieldora Maintenance Center.lnk",
        "Repair Fieldora.lnk",
        "Uninstall Fieldora.lnk",
        "Aperture.lnk",
    ):
        assert f"'{name}'" in windows
    assert "Start Menu\\Programs\\Fieldora" in windows
    assert "Start Menu\\Programs\\Aperture" in windows
    assert '"$BIN_DIR/fieldora"' in linux
    assert '"$APPLICATIONS_DIR/fieldora.desktop"' in linux
