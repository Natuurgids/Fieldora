from pathlib import Path


def test_installer_uses_v4_specific_runtime_and_library_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    frontend = (root / "scripts" / "install_aperture_frontend.ps1").read_text(encoding="utf-8")
    installer = (root / "scripts" / "install_windows.ps1").read_text(encoding="utf-8")
    manifest = (root / "scripts" / "release_manifest.py").read_text(encoding="utf-8")
    assert "'Fieldora-Library-V5'" in frontend
    assert "'Aperture-Library'" not in frontend
    assert "FieldoraData-V5" in installer
    assert '"FieldoraData-V5/"' in manifest
