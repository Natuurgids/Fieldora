from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

from natureai_next.application.project_management import (
    ProjectExportOptions,
    ProjectManagementService,
)


def _library(path: Path, media_path: Path) -> Path:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE library_assets(asset_public_id TEXT PRIMARY KEY,asset_type TEXT,
              original_filename TEXT,primary_file_public_id TEXT,title TEXT,description TEXT,mime_type TEXT);
            CREATE TABLE file_instances(public_id TEXT PRIMARY KEY,normalized_path TEXT);
            """
        )
        connection.execute(
            "INSERT INTO library_assets VALUES('sound-1','sound','field-note.mp3','file-1','Night recording','','audio/mpeg')"
        )
        connection.execute("INSERT INTO file_instances VALUES('file-1',?)", (str(media_path),))
    return path


def test_active_project_schema_upgrades_add_research_relations(tmp_path: Path) -> None:
    database = tmp_path / "science.sqlite3"
    service = ProjectManagementService(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version FROM pm_schema WHERE id=1").fetchone()[0] == 6
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"pm_research_areas", "pm_project_media", "pm_project_notes"} <= tables
    assert service.projects() == ()


def test_project_polygon_media_notes_and_embedded_export(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    project_id = service.create_project("Wetland survey", owner_id="researcher", actor_id="researcher")
    area_id = service.save_research_area(
        project_id,
        "County study boundary",
        [[3.5, 50.7], [4.2, 50.7], [4.2, 51.1], [3.5, 51.1]],
        actor_id="researcher",
    )
    area = service.research_areas(project_id)[0]
    ring = area["feature"]["geometry"]["coordinates"][0]
    assert area["area_id"] == area_id
    assert ring[0] == ring[-1]
    service.add_project_note(project_id, "Method", "Record every evening.", actor_id="researcher")
    service.attach_project_media(project_id, (("sound-1", "sound"),), actor_id="researcher")
    audio = tmp_path / "field-note.mp3"
    audio.write_bytes(b"ID3-test-audio")
    library = _library(tmp_path / "library.sqlite3", audio)
    destination = tmp_path / "wetland.zip"
    service.export_research_package(
        project_id,
        destination,
        options=ProjectExportOptions(include_original_media=True, embed_audio_video=True),
        library_database=library,
    )
    with zipfile.ZipFile(destination) as package:
        names = set(package.namelist())
        assert {
            "manifest.json", "index.html", "data/project.json", "data/tasks.json", "data/project-records.json",
            "data/notes.json", "data/media-index.csv", "data/media-index.json",
            "maps/research-areas.geojson", "maps/research-map.html",
            "media/sound/field-note.mp3",
        } <= names
        manifest = json.loads(package.read("manifest.json"))
        geojson = json.loads(package.read("maps/research-areas.geojson"))
        index = package.read("index.html").decode("utf-8")
    assert manifest["counts"]["research_areas"] == 1
    assert geojson["features"][0]["properties"]["name"] == "County study boundary"
    assert "<audio controls" in index
    assert "Record every evening." in index


def test_project_workspace_exposes_map_media_and_selective_package_controls() -> None:
    source = Path("src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    assert '"Research Area & Media"' in source
    assert '"Research Package"' in source
    assert "Attach selected Library media" in source
    assert "Import polygon GeoJSON" in source
    assert "embed_audio_video" in source
