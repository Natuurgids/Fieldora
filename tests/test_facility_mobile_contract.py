from __future__ import annotations

from pathlib import Path

import pytest

from natureai_next.application.facility_mobile import FacilityMobileService
from natureai_next.application.facility_planning import FacilityPlanningService


def test_mobile_contract_exposes_next_actions_and_destination_floorplan(tmp_path: Path) -> None:
    database = tmp_path / "science.sqlite3"
    planning = FacilityPlanningService(database)
    actor = "local-user"

    building = planning.add_location("building", "B1", "Building", actor=actor)
    source = planning.add_location("room", "R1", "Old room", building, actor=actor)
    target = planning.add_location("room", "R2", "New room", building, actor=actor)
    svg = tmp_path / "future.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600"/>', encoding="utf-8")
    drawing = planning.add_drawing(
        "Future ground floor",
        "svg",
        str(svg),
        actor,
        location_id=building,
        version="2",
        status="planned",
        operational_svg_asset_id="LIB-SVG-1",
        operational_svg_path=str(svg),
    )
    planning.add_floorplan_geometry(
        drawing,
        actor=actor,
        geometry_type="polygon",
        coordinates=((0.55, 0.2), (0.85, 0.2), (0.85, 0.7), (0.55, 0.7)),
        location_id=target,
        label="New room",
    )
    asset = planning.add_asset("OBJ-1", "Collection object", "museum-object", actor, location_id=source, owner_id=actor)
    plan = planning.create_layout_plan(
        "Future installation",
        actor=actor,
        location_id=building,
        drawing_id=drawing,
        status="planned",
    )
    planning.plan_asset_placement(plan, asset, target, actor=actor)
    campaign = planning.create_relocation_campaign("Installation move", actor=actor, plan_id=plan)
    planning.set_relocation_status(campaign, "ready", actor=actor)

    mobile = FacilityMobileService(planning)
    manifest = mobile.campaign_manifest(campaign, actor)
    assert manifest["schema"] == "fieldora.facility-relocation.v1"
    assert manifest["progress"]["total"] == 1
    step = manifest["steps"][0]
    assert step["code"] == "OBJ-1"
    assert "removed" in step["next_actions"]
    assert step["from_location_id"] == source
    assert step["to_location_id"] == target

    drawing_context = mobile.destination_drawing(step["step_id"], actor)
    assert drawing_context is not None
    assert drawing_context["drawing_id"] == drawing
    assert drawing_context["operational_svg_asset_id"] == "LIB-SVG-1"
    assert drawing_context["target_location_id"] == target
    assert drawing_context["geometry_json"]

    removed = mobile.record_state(step["step_id"], "removed", actor=actor)
    assert removed["recorded_state"] == "removed"
    assert planning.asset(asset, actor)["location_id"] == source

    with pytest.raises(ValueError, match="Invalid relocation transition"):
        mobile.record_state(step["step_id"], "displayed", actor=actor)
    assert planning.asset(asset, actor)["location_id"] == source

    transit = mobile.record_state(step["step_id"], "in_transit", actor=actor)
    assert transit["recorded_state"] == "in_transit"
    assert planning.asset(asset, actor)["location_id"] == source

    placed = mobile.record_state(step["step_id"], "placed", actor=actor)
    assert placed["recorded_state"] == "placed"
    assert planning.asset(asset, actor)["location_id"] == target

    # Retrying the same final state is intentionally idempotent for offline/mobile delivery.
    repeated = mobile.record_state(step["step_id"], "placed", actor=actor)
    assert repeated["recorded_state"] == "placed"
    assert planning.asset(asset, actor)["location_id"] == target
