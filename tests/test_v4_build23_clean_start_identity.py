from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_startup_uses_package_v4_version_not_legacy_label() -> None:
    cli = (_root() / "src/natureai_next/bootstrap/cli.py").read_text(encoding="utf-8")
    assert "from natureai_next import __version__" in cli
    assert 'version=f"Fieldora {__version__}"' in cli
    assert 'version="Aperture V3.RC1F6"' not in cli


def test_windows_installer_isolates_v4_runtime_and_launcher_state() -> None:
    installer = (_root() / "scripts/install_windows.ps1").read_text(encoding="utf-8")
    assert "Join-Path $RepositoryRoot 'FieldoraData-V5'" in installer
    assert "schema_version = 2; release_line = '4.0'" in installer
    assert "$schemaVersion -eq 2 -and $releaseLine -eq '4.0'" in installer


def test_windows_installer_creates_only_the_caller_selected_v4_library() -> None:
    installer = (_root() / "scripts/install_windows.ps1").read_text(encoding="utf-8")
    assert "Join-Path (Split-Path -Parent $DataRoot) 'Fieldora-Library-V5'" in installer
    assert "'natureai-next-admin', 'library-create'" in installer
    assert "if ($CreateDefaultLibrary)" in installer
    assert "Join-Path $RepositoryRoot 'ApertureLibrary-V4'" not in installer


def test_clean_start_library_error_is_explicit() -> None:
    lifecycle = (_root() / "src/natureai_next/infrastructure/library_lifecycle.py").read_text(
        encoding="utf-8"
    )
    assert "Normal startup never repairs or replaces library files" in lifecycle
    assert "No library data was changed" in lifecycle
