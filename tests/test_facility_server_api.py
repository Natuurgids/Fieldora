from __future__ import annotations

from pathlib import Path

from natureai_next.application.facility_mobile import FacilityMobileService
from natureai_next.application.facility_planning import FacilityPlanningService
from natureai_next.server.facility_api import FacilityApiAdapter


def _fixture(tmp_path: Path):
    planning = FacilityPlanningService(tmp_path / "science.sqlite3")
    actor = "local-user"
    building = planning.add_location("building", "B1", "Building", actor=actor)
    old_room = planning.add_location("room", "R1", "Old room", building, actor=actor)
    new_room = planning.add_location("room", "R2", "New room", building, actor=actor)
    drawing = planning.add_drawing(
        "Future plan",
        "svg",
        str(tmp_path / "future.svg"),
        actor,
        location_id=building,
        status="planned",
        version="2",
        operational_svg_asset_id="SVG-1",
        operational_svg_path=str(tmp_path / "future.svg"),
    )
    planning.add_floorplan_geometry(
        drawing,
        actor=actor,
        geometry_type="polygon",
        coordinates=((0.1, 0.1), (0.4, 0.1), (0.4, 0.4), (0.1, 0.4)),
        location_id=new_room,
    )
    asset = planning.add_asset("OBJ-1", "Object", "museum-object", actor, location_id=old_room, owner_id=actor)
    plan = planning.create_layout_plan("Future", actor=actor, location_id=building, drawing_id=drawing, status="planned")
    planning.plan_asset_placement(plan, asset, new_room, actor=actor)
    campaign = planning.create_relocation_campaign("Move", actor=actor, plan_id=plan)
    planning.set_relocation_status(campaign, "ready", actor=actor)
    mobile = FacilityMobileService(planning)
    adapter = FacilityApiAdapter(mobile)
    step = mobile.campaign_manifest(campaign, actor)["steps"][0]
    return planning, adapter, actor, asset, campaign, step


def test_server_adapter_exposes_campaign_step_destination_and_state(tmp_path: Path) -> None:
    planning, adapter, actor, asset, campaign, step = _fixture(tmp_path)

    manifest = adapter.dispatch("GET", f"/api/v1/facilities/campaigns/{campaign}", actor=actor)
    assert manifest is not None and manifest.status == 200
    assert manifest.payload["schema"] == "fieldora.facility-relocation.v1"

    destination = adapter.dispatch(
        "GET", f"/api/v1/facilities/steps/{step['step_id']}/destination", actor=actor
    )
    assert destination is not None and destination.status == 200
    assert destination.payload["operational_svg_asset_id"] == "SVG-1"

    removed = adapter.dispatch(
        "POST",
        f"/api/v1/facilities/steps/{step['step_id']}/state",
        actor=actor,
        body={"state": "removed"},
    )
    assert removed is not None and removed.status == 200
    assert planning.asset(asset, actor)["location_id"] == step["from_location_id"]

    invalid = adapter.dispatch(
        "POST",
        f"/api/v1/facilities/steps/{step['step_id']}/state",
        actor=actor,
        body={"state": "displayed"},
    )
    assert invalid is not None and invalid.status == 409
    assert invalid.payload["error"] == "invalid_transition"


def test_server_adapter_can_find_open_steps_by_scanned_operations_asset(tmp_path: Path) -> None:
    _planning, adapter, actor, asset, _campaign, step = _fixture(tmp_path)

    result = adapter.dispatch(
        "GET", f"/api/v1/facilities/resources/asset/{asset}", actor=actor
    )
    assert result is not None and result.status == 200
    assert len(result.payload) == 1
    assert result.payload[0]["step_id"] == step["step_id"]


def test_server_adapter_ignores_unrelated_routes(tmp_path: Path) -> None:
    _planning, adapter, actor, _asset, _campaign, _step = _fixture(tmp_path)
    assert adapter.dispatch("GET", "/api/v1/status", actor=actor) is None
