from pathlib import Path


def test_cleanup_utility_is_safe_by_default() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "cleanup_legacy_data.ps1").read_text(encoding="utf-8")
    assert "[string]$Mode = 'Report'" in script
    assert "Type DELETE" in script
    assert "IncludeSharedModelCaches" in script
    assert "CurrentDataRoot" in script
    assert "Remove-Item" in script
    assert (root / "Cleanup Old Aperture Data.cmd").is_file()


def test_installer_writes_authoritative_installation_config() -> None:
    text = (Path(__file__).resolve().parents[1] / "scripts" / "install_windows.ps1").read_text(
        encoding="utf-8"
    )
    assert "configRoot = Join-Path $DataRoot 'config'" in text
    assert "installation.json" in text
    assert "data_root = $DataRoot" in text
    assert "model_root = (Join-Path $DataRoot 'models')" in text
