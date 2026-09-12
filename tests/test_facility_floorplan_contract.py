from __future__ import annotations

from pathlib import Path

from natureai_next.application.operations_assets import OperationsAssetService


def test_floorplan_source_and_operational_svg_links(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FIELDORA_IDENTITY_ID", "local-user")
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "administrator")
    service = OperationsAssetService(tmp_path / "science.sqlite3")
    floor = service.add_location("floor", "G", "Ground floor")
    drawing = service.add_drawing(
        "Ground floor",
        "pdf",
        "/library/source-plan.pdf",
        "local-user",
        location_id=floor,
        version="A",
        status="draft",
        drawing_role="operational",
        library_asset_id="library-source-001",
    )
    source = service.link_drawing_source(
        drawing,
        actor="local-user",
        library_asset_id="library-source-001",
        relationship="source",
        title="Architect plan",
        source_format="pdf",
        file_path="/library/source-plan.pdf",
    )
    service.set_operational_svg(
        drawing,
        actor="local-user",
        svg_path="/library/ground-floor.svg",
        library_asset_id="library-svg-001",
    )

    row = service.drawing(drawing)
    assert row["library_asset_id"] == "library-source-001"
    assert row["operational_svg_asset_id"] == "library-svg-001"
    assert row["operational_svg_path"] == "/library/ground-floor.svg"
    assert [item["id"] for item in service.drawing_sources(drawing)] == [source]
