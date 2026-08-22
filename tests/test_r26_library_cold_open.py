from __future__ import annotations

import sqlite3
from pathlib import Path

from natureai_next.application.asset_catalog import AssetCatalogService


def _database(path: Path, count: int = 450) -> None:
    with sqlite3.connect(path) as cx:
        cx.executescript(
            """
            CREATE TABLE assets(
                id INTEGER PRIMARY KEY,
                public_id TEXT NOT NULL,
                title TEXT,
                capture_local_text TEXT,
                rating TEXT,
                media_type TEXT,
                primary_file_instance_id INTEGER,
                lifecycle_state TEXT NOT NULL,
                modified_at_us INTEGER
            );
            CREATE TABLE file_instances(
                id INTEGER PRIMARY KEY,
                normalized_path TEXT,
                mime_type TEXT,
                file_size INTEGER
            );
            """
        )
        for index in range(count):
            cx.execute(
                "INSERT INTO file_instances(id,normalized_path,mime_type,file_size) VALUES(?,?,?,?)",
                (index + 1, f"/library/photo-{index:04d}.jpg", "image/jpeg", 10),
            )
            cx.execute(
                """INSERT INTO assets(
                    id,public_id,title,capture_local_text,rating,media_type,
                    primary_file_instance_id,lifecycle_state,modified_at_us
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (index + 1, f"asset-{index:04d}", f"Photo {index:04d}", "", "", "image", index + 1, "active", count-index),
            )


def test_asset_catalog_pages_large_libraries(tmp_path: Path) -> None:
    database = tmp_path / "library.sqlite3"
    _database(database)
    service = AssetCatalogService(database)

    assert service.count_assets() == 450
    first = service.list_assets()
    second = service.list_assets(limit=200, offset=200)
    third = service.list_assets(limit=200, offset=400)

    assert len(first) == 200
    assert len(second) == 200
    assert len(third) == 50
    assert first[0].asset_id != second[0].asset_id


def test_library_page_is_lazy_and_navigation_refresh_is_not_duplicated() -> None:
    root = Path(__file__).resolve().parents[1]
    v5 = (root / "src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    application = (root / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    library = v5[v5.index("class Library(Page):"):v5.index("class Observations(Page):")]
    select_workspace = application[application.index("    def _select_workspace(self, name: str)"):application.index("        message = f\"No workspace is registered", application.index("    def _select_workspace(self, name: str)"))]

    constructor = library[:library.index(" def _normalized_type")]
    assert "self.refresh()" not in constructor
    assert "self._page_size=200" in constructor
    assert "QTimer.singleShot(0,self._perform_refresh)" in library
    assert "limit=self._page_size,offset=self._offset" in library
    assert 'if name in getattr(self, "_v5_pages", {}):\n            self._v5_pages[name].refresh()' not in select_workspace.split('item = self._navigation_items.get(name)')[0]
