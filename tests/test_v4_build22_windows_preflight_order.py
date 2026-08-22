from pathlib import Path

from release_manifest import build_manifest, verify_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_runs_preflight_before_mutable_data_creation() -> None:
    source = (ROOT / "scripts/install_windows.ps1").read_text(encoding="utf-8")
    preflight = source.index("Validating release package before installation")
    data_root_creation = source.index("New-Item -ItemType Directory -Force -Path $DataRoot")
    config_write = source.index("installation.json') -Encoding UTF8")
    assert preflight < data_root_creation < config_write
    assert "No Aperture data or installation configuration was created" in source


def test_default_windows_runtime_tree_is_not_release_inventory(tmp_path: Path) -> None:
    (tmp_path / "stable.txt").write_text("stable", encoding="utf-8")
    manifest = build_manifest(tmp_path, version="4.0.0.dev1", build="22")
    runtime = tmp_path / "ApertureData/config/installation.json"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("{}", encoding="utf-8")
    result = verify_manifest(tmp_path, manifest)
    assert result.passed, result.failures
    assert result.expected_count == 1
