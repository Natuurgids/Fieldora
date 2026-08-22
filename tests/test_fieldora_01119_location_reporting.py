from __future__ import annotations

import sqlite3
from pathlib import Path

from natureai_next.application.location_enrichment import (
    AdministrativeLocation,
    MediaLocationEnrichmentService,
)


def _database(path: Path) -> Path:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE assets(id INTEGER PRIMARY KEY,public_id TEXT,media_type TEXT,lifecycle_state TEXT);
            CREATE TABLE locations(id INTEGER PRIMARY KEY,public_id TEXT,latitude REAL,longitude REAL,
              country_code TEXT,admin_area_1 TEXT,admin_area_2 TEXT,locality TEXT,place_name TEXT,
              source TEXT,created_at_us INTEGER);
            CREATE TABLE asset_locations(asset_id INTEGER,location_id INTEGER,role TEXT,precedence INTEGER);
            CREATE TABLE sound_assets(asset_public_id TEXT PRIMARY KEY,latitude REAL,longitude REAL);
            CREATE TABLE video_assets(asset_public_id TEXT PRIMARY KEY,latitude REAL,longitude REAL);
            INSERT INTO assets VALUES(1,'sound-1','sound','active');
            INSERT INTO assets VALUES(2,'video-1','video','active');
            INSERT INTO sound_assets VALUES('sound-1',51.0500,3.7167);
            INSERT INTO video_assets VALUES('video-1',51.0500,3.7167);
            """
        )
    return path


class _Geocoder:
    def __init__(self) -> None:
        self.calls = 0

    def reverse(self, latitude: float, longitude: float) -> AdministrativeLocation:
        self.calls += 1
        assert (latitude, longitude) == (51.05, 3.7167)
        return AdministrativeLocation("BE", "East Flanders", "Ghent", "Ghent", "Ghent, Belgium")


def test_sound_and_video_coordinates_become_canonical_reporting_locations(tmp_path: Path) -> None:
    database = _database(tmp_path / "library.sqlite3")
    geocoder = _Geocoder()
    result = MediaLocationEnrichmentService(database).reconstruct_missing(
        geocoder=geocoder, request_interval_seconds=0
    )
    assert result.examined == 2
    assert result.resolved == 2
    assert geocoder.calls == 1  # identical coordinates reuse the reverse-geocode response
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """SELECT a.public_id,l.country_code,l.admin_area_1,l.locality
               FROM assets a JOIN asset_locations al ON al.asset_id=a.id
               JOIN locations l ON l.id=al.location_id ORDER BY a.id"""
        ).fetchall()
    assert rows == [
        ("sound-1", "BE", "East Flanders", "Ghent"),
        ("video-1", "BE", "East Flanders", "Ghent"),
    ]


def test_manual_sound_location_updates_detail_and_canonical_tables(tmp_path: Path) -> None:
    database = _database(tmp_path / "library.sqlite3")
    MediaLocationEnrichmentService(database).save(
        asset_public_id="sound-1",
        media_type="sound",
        latitude=50.85,
        longitude=4.35,
        administrative=AdministrativeLocation("be", "Brussels-Capital", locality="Brussels"),
    )
    with sqlite3.connect(database) as connection:
        detail = connection.execute(
            "SELECT latitude,longitude FROM sound_assets WHERE asset_public_id='sound-1'"
        ).fetchone()
        report = connection.execute(
            """SELECT l.country_code,l.admin_area_1,l.locality FROM locations l
               JOIN asset_locations al ON al.location_id=l.id WHERE al.asset_id=1"""
        ).fetchone()
    assert detail == (50.85, 4.35)
    assert report == ("BE", "Brussels-Capital", "Brussels")


def test_desktop_exposes_media_location_and_reporting_reconstruction_actions() -> None:
    media = Path("src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    reporting = Path("src/natureai_next/ui/qt/reporting.py").read_text(encoding="utf-8")
    assert 'WorkspaceAction("location", "Location…"' in media
    assert "service.reverse_asset(asset_id)" in media
    assert 'QPushButton("Reconstruct country / region…")' in reporting
    assert "service.reconstruct_missing(" in reporting
