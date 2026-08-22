import json
import re
from pathlib import Path

from natureai_next.bootstrap import aperture_launcher
from natureai_next.infrastructure.filesystem import library_lock

ROOT = Path(__file__).resolve().parents[1]


def test_windows_repair_never_recreates_environment() -> None:
    source = (ROOT / "scripts/repair_windows_integration.ps1").read_text(encoding="utf-8")
    generated = (ROOT / "scripts/install_windows.ps1").read_text(encoding="utf-8")
    assert "-RecreateEnvironment:$false" in source
    repair_block = generated[
        generated.index("$repairContent = @'") : generated.index(
            "'@", generated.index("$repairContent = @'") + 20
        )
    ]
    assert "-RecreateEnvironment:$false" in repair_block


def test_windows_environment_removal_avoids_anaconda_default_channels() -> None:
    source = (ROOT / "scripts/install_windows.ps1").read_text(encoding="utf-8")
    removal = source[
        source.index('Write-Step "Removing existing isolated environment') : source.index(
            "if ($null -eq $environmentPath)"
        )
    ]
    assert "'remove', '--all', '--yes', '--name', $EnvironmentName" in removal
    assert "'--override-channels', '--channel', 'conda-forge'" in removal
    assert "'env', 'remove'" not in removal


def test_windows_library_creation_does_not_recreate_an_existing_drive_root() -> None:
    source = (ROOT / "scripts/install_windows.ps1").read_text(encoding="utf-8")

    assert "$libraryParent = Split-Path -Parent $DefaultLibrary" in source
    assert "Test-Path -LiteralPath $libraryParent -PathType Container" in source
    assert "New-Item -ItemType Directory -Force -Path $libraryParent" in source
    assert (
        "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DefaultLibrary)"
    ) not in source


def test_release_checker_disables_bytecode_before_local_import() -> None:
    source = (ROOT / "scripts/release_candidate_check.py").read_text(encoding="utf-8")
    dont_write = source.index("sys.dont_write_bytecode = True")
    local_import = source.index("from release_manifest import")
    assert dont_write < local_import


def test_linux_installer_is_present_and_transactional() -> None:
    source = (ROOT / "scripts/install_linux.sh").read_text(encoding="utf-8")
    assert "Python 3.11 required" in source
    assert '"$VENV.new/bin/python" -m pip install' in source
    assert 'mv "$VENV.new" "$VENV"' in source
    assert 'timeout 45 "$VENV.new/bin/aperture"' in source
    assert "data.replace(old, new, 1)" in source
    assert 'verify_install.py" --require-gui' in source
    assert "APERTURE_SMOKE_TEST_SECONDS=2" in source
    assert "QT_QPA_PLATFORM" in source
    assert "SELECT 1 FROM observations LIMIT 0" in source


def test_linux_desktop_entry_uses_managed_launcher() -> None:
    source = (ROOT / "scripts/install_linux.sh").read_text(encoding="utf-8")
    assert "[Desktop Entry]" in source
    assert "Exec=$BIN_ROOT/fieldora" in source
    assert "Terminal=false" in source


def test_aperture_launcher_forwards_explicit_linux_library(monkeypatch, tmp_path) -> None:
    captured = []
    monkeypatch.setattr(aperture_launcher, "_bootstrap_log", lambda *_args: None)
    monkeypatch.setattr(
        aperture_launcher,
        "cli_main",
        lambda args: captured.append(list(args)) or 0,
    )
    library = tmp_path / "Library"
    assert aperture_launcher.main(["--library", str(library), "--no-update-check"]) == 0
    assert captured == [["--library", str(library), "--no-update-check"]]


def test_normal_main_window_close_explicitly_quits_qt() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    close_event = source[source.index("    def closeEvent") : source.index("\n\ndef run_desktop")]
    assert "QTimer.singleShot(0, app.quit)" in close_event
    assert "self.findChildren(QThread)" in close_event
    assert "thread.wait(10000)" in close_event
    run_desktop = source[source.index("def run_desktop") :]
    assert "finally:\n        # Some Linux Qt platform plugins" in run_desktop
    assert "on_about_to_quit()" in run_desktop


def test_desktop_enrichment_never_uses_core_library_database() -> None:
    cli = (ROOT / "src/natureai_next/bootstrap/cli.py").read_text(encoding="utf-8")
    application = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert (
        'enrichment_database_path=container.paths.subsystem_databases_dir / "enrichment.sqlite3"'
        in cli
    )
    assert (
        "build_desktop_enrichment_controller(\n            self._enrichment_database_path"
        in application
    )


def test_repair16_version_is_unique() -> None:
    versions = {
        (ROOT / "VERSION").read_text().strip(),
        re.search(r'version = "([^"]+)"', (ROOT / "pyproject.toml").read_text()).group(1),
        re.search(
            r'__version__ = "([^"]+)"', (ROOT / "src/natureai_next/__init__.py").read_text()
        ).group(1),
    }
    assert versions == {"5.4.0"}


def test_library_lock_recovers_reused_pid_with_different_start_id(monkeypatch, tmp_path) -> None:
    path = tmp_path / ".natureai-next.lock"
    path.write_text(
        json.dumps(
            {
                "pid": 73,
                "host": library_lock.socket.gethostname(),
                "created_at_us": 1,
                "process_start_id": "old-process",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(library_lock.os, "kill", lambda _pid, _signal: None)
    monkeypatch.setattr(library_lock, "_process_start_id", lambda _pid: "new-process")

    assert library_lock.recover_stale_library_lock(path)
    assert not path.exists()
