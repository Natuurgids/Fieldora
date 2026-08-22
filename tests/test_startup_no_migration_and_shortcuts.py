from __future__ import annotations

from pathlib import Path


def test_existing_library_open_is_non_mutating() -> None:
    source = Path("src/natureai_next/infrastructure/library_lifecycle.py").read_text(
        encoding="utf-8"
    )
    open_body = source.split("def open(self, root: Path)", 1)[1]
    assert "MigrationRunner(CORE_MIGRATIONS" not in open_body
    assert "connect(read_only=True)" in open_body
    assert "No library data was changed" in open_body


def test_windows_shortcuts_use_packaged_entry_points() -> None:
    source = Path("scripts/install_windows.ps1").read_text(encoding="utf-8")
    assert "Scripts\\fieldora-maintenance-center.exe" in source
    assert "Name = 'Fieldora Maintenance Center'; Target = $powerShellExecutable" in source
    assert "Start-Process -FilePath $executable" in source
    assert "'--log-level', 'DEBUG', '--diagnostics', '--no-update-check'" in source
    assert "& $executable -m natureai_next.bootstrap.cli" not in source
