from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from natureai_next.application.facility_library import FacilityDrawingLibraryBridge
from natureai_next.application.facility_planning import FacilityPlanningService


def _library_database(path: Path, svg_path: Path, pdf_path: Path) -> None:
    with sqlite3.connect(path) as cx:
        cx.executescript(
            """
            CREATE TABLE assets(
                id INTEGER PRIMARY KEY,
                public_id TEXT NOT NULL UNIQUE,
                title TEXT,
                caption TEXT,
                user_notes TEXT,
                lifecycle_state TEXT NOT NULL,
                modified_at_us INTEGER NOT NULL,
                media_type TEXT,
                capture_local_text TEXT,
                rating TEXT,
                primary_file_instance_id INTEGER
            );
            CREATE TABLE file_instances(
                id INTEGER PRIMARY KEY,
                normalized_path TEXT,
                mime_type TEXT,
                file_size INTEGER,
                sha256 TEXT
            );
            """
        )
        cx.execute(
            "INSERT INTO file_instances VALUES(1,?,?,?,?)",
            (str(svg_path), "image/svg+xml", 100, "svg-digest"),
        )
        cx.execute(
            "INSERT INTO file_instances VALUES(2,?,?,?,?)",
            (str(pdf_path), "application/pdf", 200, "pdf-digest"),
        )
        cx.execute(
            "INSERT INTO assets VALUES(1,'LIB-SVG','Ground floor operational SVG','','','active',1,'document','','',1)"
        )
        cx.execute(
            "INSERT INTO assets VALUES(2,'LIB-PDF','Architect ground floor drawing','','','active',2,'document','','',2)"
        )


def test_drawing_revision_references_library_source_and_operational_svg(tmp_path: Path) -> None:
    science = tmp_path / "science.sqlite3"
    library = tmp_path / "library.sqlite3"
    svg = tmp_path / "ground-floor.svg"
    pdf = tmp_path / "architect.pdf"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>', encoding="utf-8")
    pdf.write_bytes(b"%PDF-test")
    _library_database(library, svg, pdf)

    operations = FacilityPlanningService(science)
    actor = "local-user"
    building = operations.add_location("building", "B1", "Building", actor=actor)
    drawing = operations.add_drawing(
        "Ground floor",
        "pdf",
        str(pdf),
        actor,
        location_id=building,
        version="7",
        status="planned",
    )
    bridge = FacilityDrawingLibraryBridge(operations, library)

    source_id = bridge.link_source_asset(
        drawing,
        "LIB-PDF",
        actor=actor,
        relationship="architectural",
    )
    assert source_id
    bridge.set_operational_svg_asset(drawing, "LIB-SVG", actor=actor)

    context = bridge.drawing_library_context(drawing, actor)
    assert context["drawing"]["operational_svg_asset_id"] == "LIB-SVG"
    assert context["drawing"]["operational_svg_path"] == str(svg)
    assert context["operational_svg"]["public_id"] == "LIB-SVG"
    assert context["sources"][0]["library_asset_id"] == "LIB-PDF"
    assert context["sources"][0]["relationship"] == "architectural"
    assert context["sources"][0]["library"]["sha256"] == "pdf-digest"


def test_non_svg_library_asset_cannot_be_operational_floorplan(tmp_path: Path) -> None:
    science = tmp_path / "science.sqlite3"
    library = tmp_path / "library.sqlite3"
    svg = tmp_path / "ground-floor.svg"
    pdf = tmp_path / "architect.pdf"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    pdf.write_bytes(b"%PDF-test")
    _library_database(library, svg, pdf)

    operations = FacilityPlanningService(science)
    actor = "local-user"
    building = operations.add_location("building", "B1", "Building", actor=actor)
    drawing = operations.add_drawing("Ground floor", "pdf", str(pdf), actor, location_id=building)
    bridge = FacilityDrawingLibraryBridge(operations, library)

    with pytest.raises(ValueError, match="must be an SVG"):
        bridge.set_operational_svg_asset(drawing, "LIB-PDF", actor=actor)
