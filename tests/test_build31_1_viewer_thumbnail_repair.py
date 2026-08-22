from pathlib import Path

from PIL import Image

from natureai_next.infrastructure.imaging.catalog_thumbnails import PillowCatalogThumbnailProvider


def test_gallery_worker_persists_thumbnail_and_viewer_can_decode_original(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    Image.new("RGB", (640, 480), "white").save(source, format="JPEG")
    provider = PillowCatalogThumbnailProvider(thumbnail_root=tmp_path / "thumbs", library_root=tmp_path)

    stable = provider.asset_cache_path("asset-public-id")
    assert stable is not None
    assert provider.load(source_path=source, cached_path=stable, max_size=192) is not None
    assert stable.is_file()
    data = provider.load(source_path=source, cached_path=None, max_size=900)
    assert data is not None


def test_viewer_resolves_persisted_derivatives_and_uses_70_30_split() -> None:
    source = Path("src/natureai_next/ui/qt/viewer.py").read_text(encoding="utf-8")
    assert 'derivative_path(self._public_id, "preview")' in source
    assert 'derivative_path(self._public_id, "thumbnail")' in source
    assert "splitter.setStretchFactor(0, 7)" in source
    assert "splitter.setStretchFactor(1, 3)" in source
    assert "int(self.width() * 0.30)" in source


def test_thumbnail_worker_refreshes_derivative_path() -> None:
    source = Path("src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")
    assert 'self._catalog.derivative_path(self._public_id, "thumbnail")' in source
