from pathlib import Path


ROOT = Path(__file__).parents[1]
INSTALL = (ROOT / "scripts/install_linux.sh").read_text(encoding="utf-8")
UNINSTALL = (ROOT / "scripts/uninstall_linux.sh").read_text(encoding="utf-8")


def test_linux_uses_isolated_fieldora_v5_paths() -> None:
    assert "/FieldoraV5" in INSTALL
    assert "Fieldora-Library-V5" in INSTALL
    assert "/Aperture/runtime" not in INSTALL


def test_installed_artifacts_all_have_uninstall_cleanup() -> None:
    for artifact in (
        "fieldora", "fieldora-uninstall", "fieldora.desktop",
        "uninstall_linux.sh", "share/fieldora.ico",
    ):
        assert artifact in INSTALL
        assert artifact in UNINSTALL


def test_linux_matches_windows_uninstall_modes() -> None:
    for option in ("--package-only", "--remove-runtime", "--full-reset"):
        assert option in UNINSTALL
    assert 'MODE="package"' in UNINSTALL
    assert 'MODE="runtime"' in UNINSTALL
    assert 'MODE="reset"' in UNINSTALL


def test_linux_cleanup_is_bounded_and_preserves_research_data() -> None:
    assert '"$value" != /' in UNINSTALL
    assert '"$value" != "$HOME"' in UNINSTALL
    assert '"$value" != "$xdg_root"' in UNINSTALL
    assert 'rm -rf -- "$INSTALL_ROOT"' in UNINSTALL
    assert 'if [[ "$MODE" == reset ]]' in UNINSTALL
    assert "Research libraries, photographs, projects, backups and exports were preserved" in UNINSTALL


def test_linux_refreshes_desktop_registration() -> None:
    assert "update-desktop-database" in INSTALL
    assert "update-desktop-database" in UNINSTALL
