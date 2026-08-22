from __future__ import annotations

from pathlib import Path

INSTALLER = Path("scripts/install_windows.ps1")
UNINSTALLER = Path("scripts/uninstall_windows.ps1")


def test_installer_creates_normal_and_debug_startup_links() -> None:
    source = INSTALLER.read_text(encoding="utf-8")
    assert "@{ Name = 'Fieldora'; Target = $apertureLauncher" in source
    assert "@{ Name = 'Fieldora (Debug)'; Target = $powerShellExecutable" in source
    assert "Start Fieldora with NatureAI_Next debug logging" in source
    assert "if ($DesktopShortcuts)" in source
    assert "if ($StartMenuShortcuts)" in source


def test_debug_launcher_captures_reproducible_support_bundle() -> None:
    source = INSTALLER.read_text(encoding="utf-8")
    assert "logs\\debug-sessions" in source
    assert "-RedirectStandardOutput $stdoutLog" in source
    assert "-RedirectStandardError $stderrLog" in source
    assert "Set-Content -LiteralPath $consoleLog" in source
    assert "'--log-level', 'DEBUG', '--diagnostics', '--no-update-check'" in source
    assert "session.json" in source
    assert "result.json" in source
    assert "natureai-next.jsonl" in source
    assert "Compress-Archive" in source
    assert "Aperture-debug-$sessionStamp.zip" in source


def test_uninstaller_removes_normal_and_debug_links() -> None:
    source = UNINSTALLER.read_text(encoding="utf-8")
    assert "'Aperture.lnk'" in source
    assert "'Aperture (Debug).lnk'" in source
    assert "Microsoft\\Windows\\Start Menu\\Programs\\Aperture" in source
    assert "Remove machine-local NatureAI Next launchers" in source
