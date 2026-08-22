from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image

from natureai_next.application.catalog_maintenance import CatalogMaintenanceService
from natureai_next.infrastructure.imaging.catalog_thumbnails import PillowCatalogThumbnailProvider


def test_stable_asset_thumbnail_is_generated_once_and_reused_offline(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    Image.new("RGB", (640, 480), "white").save(source)
    provider = PillowCatalogThumbnailProvider(thumbnail_root=tmp_path / "cache")
    cached = provider.asset_cache_path("asset-public-id")
    assert cached is not None
    first = provider.load(source_path=source, cached_path=cached, max_size=192)
    assert first is not None and cached.is_file()
    source.unlink()
    assert provider.load(source_path=source, cached_path=cached, max_size=192) == first


def test_permanent_delete_detaches_restricting_asset_references() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE assets(id INTEGER PRIMARY KEY);
        CREATE TABLE history(id INTEGER PRIMARY KEY, asset_id INTEGER REFERENCES assets(id));
        CREATE TABLE required_child(id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE RESTRICT);
        INSERT INTO assets(id) VALUES(1);
        INSERT INTO history(id,asset_id) VALUES(1,1);
        INSERT INTO required_child(id,asset_id) VALUES(1,1);
        """
    )
    CatalogMaintenanceService._detach_restricting_asset_references(connection, 1)
    connection.execute("DELETE FROM assets WHERE id=1")
    assert connection.execute("SELECT asset_id FROM history").fetchone()[0] is None
    assert connection.execute("SELECT COUNT(*) FROM required_child").fetchone()[0] == 0
