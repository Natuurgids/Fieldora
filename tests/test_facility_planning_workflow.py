from __future__ import annotations

import sqlite3
from pathlib import Path

from natureai_next.application.facility_planning import FacilityPlanningService


def test_future_layout_does_not_change_live_location_until_final_move(tmp_path: Path) -> None:
    database = tmp_path / "science.sqlite3"
    service = FacilityPlanningService(database)
    actor = "local-user"

    building = service.add_location("building", "B1", "Main building", actor=actor)
    current_room = service.add_location("room", "R1", "Current room", building, actor=actor)
    future_room = service.add_location("room", "R2", "Future room", building, actor=actor)

    asset = service.add_asset(
        "EQ-001",
        "Reference cabinet",
        "cabinet",
        actor,
        location_id=current_room,
        owner_id=actor,
    )
    drawing = service.add_drawing(
        "Ground floor future layout",
        "svg",
        str(tmp_path / "ground-floor.svg"),
        actor,
        location_id=building,
        version="2",
        status="planned",
        operational_svg_path=str(tmp_path / "ground-floor.svg"),
    )
    plan = service.create_layout_plan(
        "Renovation layout",
        actor=actor,
        location_id=building,
        drawing_id=drawing,
        version="2027-A",
        status="planned",
        effective_at="2027-04-01T08:00:00",
    )

    placement = service.plan_asset_placement(plan, asset, future_room, actor=actor)
    assert placement
    assert service.asset(asset, actor)["location_id"] == current_room

    overview = service.current_and_planned_location(
        resource_type="operations.asset",
        resource_id=asset,
        actor=actor,
    )
    assert overview["current_location_id"] == current_room
    assert overview["planned"][0]["target_location_id"] == future_room

    campaign = service.create_relocation_campaign(
        "Move collection for renovation",
        actor=actor,
        plan_id=plan,
    )
    steps = service.relocation_steps(campaign, actor)
    assert len(steps) == 1
    step = steps[0]
    assert step["from_location_id"] == current_room
    assert step["to_location_id"] == future_room

    service.record_relocation_step_state(step["id"], "removed", actor=actor)
    assert service.asset(asset, actor)["location_id"] == current_room

    service.record_relocation_step_state(
        step["id"],
        "placed",
        actor=actor,
        moved_at="2027-04-01T11:30:00",
    )
    assert service.asset(asset, actor)["location_id"] == future_room

    progress = service.relocation_progress(campaign, actor)
    assert progress == {"total": 1, "completed": 1, "outstanding": 0, "exceptions": 0}

    movements = service.resource_movements("operations.asset", asset, actor)
    assert len(movements) == 1
    assert movements[0]["from_location_id"] == current_room
    assert movements[0]["to_location_id"] == future_room


def test_relocation_campaign_populates_every_planned_resource(tmp_path: Path) -> None:
    database = tmp_path / "science.sqlite3"
    service = FacilityPlanningService(database)
    actor = "local-user"

    site = service.add_location("site", "S1", "Site", actor=actor)
    source = service.add_location("room", "A", "Source", site, actor=actor)
    target = service.add_location("room", "B", "Target", site, actor=actor)
    plan = service.create_layout_plan("Lab move", actor=actor, location_id=site)

    first = service.add_asset("LAB-1", "Freezer 1", "freezer", actor, location_id=source, owner_id=actor)
    second = service.add_asset("LAB-2", "Freezer 2", "freezer", actor, location_id=source, owner_id=actor)
    service.plan_asset_placement(plan, first, target, actor=actor, sequence=10)
    service.plan_asset_placement(plan, second, target, actor=actor, sequence=20)

    campaign = service.create_relocation_campaign("Laboratory relocation", actor=actor, plan_id=plan)
    picklist = service.relocation_picklist(campaign, actor)

    assert [row["display_code"] for row in picklist] == ["LAB-1", "LAB-2"]
    assert all(row["from_path"] for row in picklist)
    assert all(row["to_path"] for row in picklist)


def test_schema_migration_adds_floorplan_columns_to_existing_database(tmp_path: Path) -> None:
    database = tmp_path / "science.sqlite3"
    with sqlite3.connect(database) as cx:
        cx.executescript(
            """
            CREATE TABLE ops_locations(
                id TEXT PRIMARY KEY,parent_id TEXT,location_type TEXT NOT NULL,code TEXT NOT NULL,name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',drawing_id TEXT,sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,
                UNIQUE(parent_id,code)
            );
            CREATE TABLE ops_building_drawings(
                id TEXT PRIMARY KEY,location_id TEXT,title TEXT NOT NULL,source_format TEXT NOT NULL,file_path TEXT NOT NULL,
                preview_path TEXT NOT NULL DEFAULT '',version TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'active',
                effective_at TEXT NOT NULL DEFAULT '',superseded_at TEXT NOT NULL DEFAULT '',width REAL,height REAL,
                metadata_json TEXT NOT NULL DEFAULT '{}',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,
                updated_at_us INTEGER NOT NULL
            );
            CREATE TABLE ops_drawing_markers(
                id TEXT PRIMARY KEY,drawing_id TEXT NOT NULL,location_id TEXT,asset_id TEXT,marker_code TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',x REAL NOT NULL,y REAL NOT NULL,width REAL NOT NULL DEFAULT 0,
                height REAL NOT NULL DEFAULT 0,geometry_json TEXT NOT NULL DEFAULT '{}',created_at_us INTEGER NOT NULL,
                updated_at_us INTEGER NOT NULL
            );
            """
        )

    FacilityPlanningService(database)
    with sqlite3.connect(database) as cx:
        drawing_columns = {row[1] for row in cx.execute("PRAGMA table_info(ops_building_drawings)")}
        marker_columns = {row[1] for row in cx.execute("PRAGMA table_info(ops_drawing_markers)")}

    assert {"drawing_role", "library_asset_id", "operational_svg_asset_id", "operational_svg_path"} <= drawing_columns
    assert {"geometry_type", "coordinate_space", "layer", "z_order", "active"} <= marker_columns
