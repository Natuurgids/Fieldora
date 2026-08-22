from __future__ import annotations

import sqlite3
from pathlib import Path

from natureai_next.application.asset_catalog import AssetCatalogService, classify_asset_type


def _database(path: Path) -> Path:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE assets(
                id INTEGER PRIMARY KEY, public_id TEXT UNIQUE, media_type TEXT,
                lifecycle_state TEXT, primary_file_instance_id INTEGER,
                capture_local_text TEXT, rating INTEGER, title TEXT, caption TEXT,
                user_notes TEXT, modified_at_us INTEGER
            );
            CREATE TABLE file_instances(
                id INTEGER PRIMARY KEY, asset_id INTEGER, normalized_path TEXT,
                mime_type TEXT, file_size INTEGER
            );
            CREATE TABLE library_assets(asset_public_id TEXT PRIMARY KEY, asset_type TEXT);
            CREATE TABLE observations(id INTEGER PRIMARY KEY, public_id TEXT, asset_id INTEGER, modified_at_us INTEGER);
            CREATE TABLE collections(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE collection_assets(collection_id INTEGER, asset_id INTEGER);
            CREATE TABLE tags(id INTEGER PRIMARY KEY, display_name TEXT);
            CREATE TABLE asset_tags(asset_id INTEGER, tag_id INTEGER);
            """
        )
        fixtures = [
            (1, 'photo-1', 'image', 1, 'bird.jpg', 'image/jpeg', 'photo'),
            (2, 'sound-1', 'image', 2, 'bird.wav', 'audio/wav', 'sound'),
            (3, 'video-1', 'image', 3, 'bird.mp4', 'video/mp4', 'video'),
            (4, 'document-1', 'image', 4, 'report.pdf', 'application/pdf', 'document'),
            (5, 'map-1', 'image', 5, 'survey.gpkg', 'application/octet-stream', ''),
            (6, 'archive-1', 'image', 6, 'evidence.zip', 'application/zip', ''),
        ]
        for index, public_id, legacy, file_id, filename, mime, catalog_type in fixtures:
            connection.execute(
                "INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (index, public_id, legacy, 'active', file_id, '', None, filename, '', '', index),
            )
            connection.execute(
                "INSERT INTO file_instances VALUES(?,?,?,?,?)",
                (file_id, index, filename, mime, index * 100),
            )
            if catalog_type:
                connection.execute("INSERT INTO library_assets VALUES(?,?)", (public_id, catalog_type))
        connection.execute("INSERT INTO observations VALUES(1,'obs-1',1,1)")
        connection.execute("INSERT INTO collections VALUES(1,'Evidence')")
        connection.execute("INSERT INTO collection_assets VALUES(1,1)")
        connection.execute("INSERT INTO tags VALUES(1,'Bird')")
        connection.execute("INSERT INTO asset_tags VALUES(1,1)")
    return path


def test_asset_type_classification_prefers_real_mime_and_extension() -> None:
    assert classify_asset_type(mime_type='audio/wav', path='x.wav', media_type='image') == 'sound'
    assert classify_asset_type(mime_type='video/mp4', path='x.mp4', media_type='image') == 'video'
    assert classify_asset_type(mime_type='application/pdf', path='x.pdf', media_type='image') == 'document'
    assert classify_asset_type(mime_type='application/octet-stream', path='x.gpkg', media_type='image') == 'map'
    assert classify_asset_type(mime_type='application/zip', path='x.zip', media_type='image') == 'archive'


def test_unified_catalog_lists_every_media_type_and_filters(tmp_path: Path) -> None:
    service = AssetCatalogService(_database(tmp_path / 'library.sqlite3'))
    assert [row.asset_type for row in service.list_assets()] == ['archive', 'map', 'document', 'video', 'sound', 'photo']
    assert [row.asset_id for row in service.list_assets(asset_type='sound')] == ['sound-1']
    assert [row.asset_id for row in service.list_assets(asset_type='other')] == ['archive-1']
    assert [row.asset_id for row in service.list_assets(search='report')] == ['document-1']


def test_exact_asset_route_uses_catalog_type_and_relationships(tmp_path: Path) -> None:
    service = AssetCatalogService(_database(tmp_path / 'library.sqlite3'))
    assert service.asset_type('sound-1') == 'sound'
    assert service.asset_type('document-1') == 'document'
    assert service.relationships('photo-1') == [
        ('Observation', 'obs-1'), ('Collection', 'Evidence'), ('Tag', 'Bird')
    ]


def test_library_keeps_original_specialized_workspace_routes() -> None:
    v5 = Path('src/natureai_next/ui/qt/v5_desktop.py').read_text(encoding='utf-8')
    library = v5[v5.index('class Library(Page):'):v5.index('class Observations(Page):')]
    for route in ("('Photos','Photos')", "('Sounds','Sounds')", "('Videos','Videos')", "('Documents','Documents')"):
        assert route in library
    assert 'AssetCatalogService' in library
    application = Path('src/natureai_next/ui/qt/application.py').read_text(encoding='utf-8')
    assert 'AssetCatalogService(self._library_database_path).asset_type(identity)' in application
    assert '"sound": "Sounds"' in application
    assert '"video": "Videos"' in application
    assert '"document": "Documents"' in application
