from pathlib import Path

from natureai_next.infrastructure.imaging.catalog_thumbnails import PillowCatalogThumbnailProvider


def test_larger_persisted_thumbnail_is_valid_for_smaller_gallery_request(tmp_path):
    from PIL import Image
    path = tmp_path / "thumb.jpg"
    Image.new("RGB", (384, 256)).save(path, "JPEG")
    provider = PillowCatalogThumbnailProvider(library_root=tmp_path)
    assert provider.load(source_path=None, cached_path=path, max_size=192)


def test_windows_installer_uses_maintenance_wrapper():
    source = (Path(__file__).parents[1] / "scripts" / "install_windows.ps1").read_text(encoding="utf-8")
    assert "start_maintenance_center.ps1" in source
    assert "Resolve-NatureAILibrary" in source
    assert "Name = 'Fieldora Maintenance Center'; Target = $powerShellExecutable" in source


def test_application_accepts_console_script_as_direct_maintenance_entry():
    source = (Path(__file__).parents[1] / "src" / "natureai_next" / "ui" / "qt" / "application.py").read_text(encoding="utf-8")
    assert 'Scripts" / "aperture-maintenance-center.exe"' in source
    assert "if direct_entry:" in source
