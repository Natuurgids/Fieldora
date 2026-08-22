from __future__ import annotations

from pathlib import Path


def test_windows_builder_creates_recognizable_fieldora_processes() -> None:
    source = Path("scripts/build_aperture_windows_installer.ps1").read_text(
        encoding="utf-8-sig"
    )
    for name in (
        "Fieldora",
        "Fieldora.Maintenance",
        "Fieldora.Manuals",
        "Fieldora.Server",
        "Fieldora.Worker",
        "Fieldora.Updater",
        "Fieldora.Recovery",
    ):
        assert f"Build-App -Name '{name}'" in source
    assert "OutputBaseFilename=Fieldora-$Version-Setup" in source
    assert '#define MyAppExeName "Fieldora.exe"' in source


def test_native_executables_receive_windows_version_metadata() -> None:
    source = Path("scripts/build_aperture_windows_installer.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "'--version-file', $versionFile" in source
    for field in (
        "CompanyName",
        "FileDescription",
        "FileVersion",
        "OriginalFilename",
        "ProductName",
        "ProductVersion",
    ):
        assert f"StringStruct('{field}'" in source


def test_runtime_is_frozen_not_renamed() -> None:
    source = Path("scripts/build_aperture_windows_installer.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert "'pyinstaller', '--noconfirm', '--clean', '--onedir'" in source
    installer = Path("scripts/install_windows.ps1").read_text(encoding="utf-8-sig")
    assert "Copying pythonw.exe under friendly names is unreliable" in installer
