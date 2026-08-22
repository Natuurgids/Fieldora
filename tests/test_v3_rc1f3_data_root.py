from pathlib import Path

from natureai_next.application.launcher_configuration import launcher_configuration_path
from natureai_next.bootstrap.paths import resolve_application_paths


def test_data_root_environment_controls_application_storage(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "ApertureData"
    monkeypatch.setenv("APERTURE_DATA_ROOT", str(root))
    paths = resolve_application_paths()
    assert paths.local_root == root.resolve()
    assert paths.models_dir == root.resolve() / "models"
    assert paths.cache_dir == root.resolve() / "cache"
    assert paths.logs_dir == root.resolve() / "logs"
    assert launcher_configuration_path() == root.resolve() / "roaming" / "launcher.json"


def test_installer_routes_large_caches_to_data_root() -> None:
    text = (Path(__file__).resolve().parents[1] / "scripts" / "install_windows.ps1").read_text(
        encoding="utf-8"
    )
    assert "[string]$DataRoot" in text
    assert "APERTURE_DATA_ROOT" in text
    assert "HUGGINGFACE_HUB_CACHE" in text
    assert "TORCH_HOME" in text
    assert "Join-Path $DataRoot 'launchers'" in text
