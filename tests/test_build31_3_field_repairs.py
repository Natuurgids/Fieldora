from pathlib import Path


def test_catalog_resolves_derivatives_against_library_root() -> None:
    source = Path("src/natureai_next/infrastructure/database/catalog_gui.py").read_text(
        encoding="utf-8"
    )
    assert "self._library_root = factory.database_path.parent" in source
    assert "path = self._library_root / path" in source
    assert 'thumbnail_path=self._derivative_path(r["thumbnail_path"])' in source
    assert 'return None if row is None else self._derivative_path' in source


def test_import_is_visible_in_activity_center() -> None:
    source = Path("src/natureai_next/ui/qt/importing.py").read_text(encoding="utf-8")
    assert 'kind="import.media"' in source
    assert "Import queued in Activity Center" in source
    assert "self._center.changed.connect(self._activity_changed)" in source
    assert "cancelled()" in source


def test_backup_runs_in_activity_center_without_wait_cursor() -> None:
    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert 'kind="backup.library"' in source
    assert "Backup queued in Activity Center" in source
    assert "QApplication.setOverrideCursor" not in source[source.index("def back_up_library"):source.index("def _select_backup_file")]


def test_restore_launches_maintenance_center_with_visible_restore_intent() -> None:
    application = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    maintenance = Path("src/natureai_next/ui/qt/maintenance_center.py").read_text(
        encoding="utf-8"
    )
    assert '"--intent", "restore"' in application
    assert 'QGroupBox("Backup and restore")' in maintenance
    assert "ensureWidgetVisible(self.backup_group" in maintenance
    assert "Restore Library — select a verified backup" in maintenance
    assert 'choices=("restore", "maintenance")' in maintenance


def test_library_operation_families_are_independently_serialized() -> None:
    source = Path("src/natureai_next/ui/qt/activity.py").read_text(encoding="utf-8")
    assert '"import.media": 1' in source
    assert '"backup.library": 1' in source
    assert '"storage.verify": 1' in source
