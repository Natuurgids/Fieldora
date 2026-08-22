from pathlib import Path


ROOT = Path(__file__).parents[1]
INSTALL = (ROOT / "scripts/install_windows.ps1").read_text(encoding="utf-8")
UNINSTALL = (ROOT / "scripts/uninstall_windows.ps1").read_text(encoding="utf-8")


def test_every_v5_shortcut_created_by_installer_has_cleanup_identity() -> None:
    for name in (
        "Fieldora V5", "Fieldora V5 (Debug)",
        "Fieldora V5 - Select Library", "Fieldora V5 Maintenance Center",
        "Repair Fieldora V5", "Uninstall Fieldora V5",
    ):
        assert name in INSTALL
        assert f"'{name}.lnk'" in UNINSTALL


def test_active_registration_and_launcher_locations_are_removed() -> None:
    assert "Uninstall\\Fieldora V5" in INSTALL
    assert "Uninstall\\Fieldora V5" in UNINSTALL
    assert "FieldoraData-V5\\launchers" in UNINSTALL
    assert "$PSScriptRoot" in UNINSTALL and "-ieq 'launchers'" in UNINSTALL


def test_pinned_shortcuts_and_shell_icon_cache_are_cleaned() -> None:
    assert "User Pinned\\TaskBar" in UNINSTALL
    assert "ie4uinit.exe" in UNINSTALL


def test_uninstall_keeps_authoritative_research_data_by_default() -> None:
    assert "NatureAI libraries and source photographs were not touched" in UNINSTALL
    assert "if ($RemoveApplicationData)" in UNINSTALL
