from __future__ import annotations

import json
from pathlib import Path

from natureai_next.application.operations_assets import OperationsAssetService


def _service(tmp_path: Path, monkeypatch) -> OperationsAssetService:
    monkeypatch.setenv("FIELDORA_IDENTITY_ID", "local-user")
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "administrator")
    return OperationsAssetService(tmp_path / "science.sqlite3")


def test_floorplan_geometry_is_linked_to_canonical_location(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    building = service.add_location("building", "B1", "Main building")
    floor = service.add_location("floor", "F1", "First floor", parent_id=building)
    room = service.add_location("room", "101", "Archive room", parent_id=floor)
    drawing = service.add_drawing(
        "First floor operational plan",
        "svg",
        "/library/floor-1.svg",
        "local-user",
        location_id=floor,
        version="2.0",
        status="planned",
        drawing_role="operational",
        library_asset_id="asset-source-pdf",
        operational_svg_asset_id="asset-operational-svg",
        operational_svg_path="/library/floor-1-operational.svg",
    )

    geometry_id = service.add_floorplan_geometry(
        drawing,
        actor="local-user",
        geometry_type="polygon",
        coordinates=((0.10, 0.10), (0.45, 0.10), (0.45, 0.40), (0.10, 0.40)),
        location_id=room,
        label="Archive room",
    )

    rows = service.geometries_for_location(room, actor="local-user", drawing_id=drawing)
    assert len(rows) == 1
    assert rows[0]["id"] == geometry_id
    assert rows[0]["geometry_type"] == "polygon"
    assert rows[0]["coordinate_space"] == "normalized"
    payload = json.loads(rows[0]["geometry_json"])
    assert payload["coordinates"][0] == [0.1, 0.1]

    locations = service.locations_on_drawing(drawing)
    assert [row["id"] for row in locations] == [room]
    assert locations[0]["geometry_id"] == geometry_id


def test_activating_revision_supersedes_previous_current_revision(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    floor = service.add_location("floor", "F2", "Second floor")
    old = service.add_drawing(
        "Second floor",
        "svg",
        "/library/f2-v1.svg",
        "local-user",
        location_id=floor,
        version="1",
        status="current",
    )
    new = service.add_drawing(
        "Second floor",
        "svg",
        "/library/f2-v2.svg",
        "local-user",
        location_id=floor,
        version="2",
        status="approved",
    )

    service.activate_drawing_revision(new, actor="local-user", effective_at="2026-09-01")
    drawings = {row["id"]: row for row in service.drawings()}

    assert drawings[new]["status"] == "current"
    assert drawings[new]["effective_at"] == "2026-09-01"
    assert drawings[old]["status"] == "superseded"
    assert drawings[old]["superseded_at"] == "2026-09-01"


def test_location_context_prefers_exact_current_geometry(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    building = service.add_location("building", "HQ", "Headquarters")
    floor = service.add_location("floor", "03", "Third floor", parent_id=building)
    room = service.add_location("room", "3.14", "Specimen room", parent_id=floor)
    current = service.add_drawing(
        "Third floor current",
        "svg",
        "/plans/current.svg",
        "local-user",
        location_id=floor,
        version="4",
        status="current",
        operational_svg_path="/plans/current.svg",
    )
    planned = service.add_drawing(
        "Third floor future",
        "svg",
        "/plans/future.svg",
        "local-user",
        location_id=floor,
        version="5",
        status="planned",
        operational_svg_path="/plans/future.svg",
    )
    service.add_floorplan_geometry(
        current,
        actor="local-user",
        geometry_type="rectangle",
        coordinates=((0.2, 0.3), (0.4, 0.6)),
        location_id=room,
    )
    service.add_floorplan_geometry(
        planned,
        actor="local-user",
        geometry_type="rectangle",
        coordinates=((0.5, 0.3), (0.8, 0.7)),
        location_id=room,
    )

    context = service.location_drawing_context(room, actor="local-user")
    assert context is not None
    assert context["id"] == current
    assert context["status"] == "current"

    context_with_future = service.location_drawing_context(room, actor="local-user", include_planned=True)
    assert context_with_future is not None
    assert context_with_future["id"] == current


def test_floorplan_rejects_out_of_range_coordinates(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    room = service.add_location("room", "R1", "Room")
    drawing = service.add_drawing("Room", "svg", "/plan.svg", "local-user", location_id=room)

    try:
        service.add_floorplan_geometry(
            drawing,
            actor="local-user",
            geometry_type="polygon",
            coordinates=((0.0, 0.0), (1.1, 0.0), (0.5, 0.5)),
            location_id=room,
        )
    except ValueError as exc:
        assert "normalized" in str(exc)
    else:  # pragma: no cover - explicit contract guard
        raise AssertionError("out-of-range geometry must be rejected")
