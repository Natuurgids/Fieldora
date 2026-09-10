from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_facility_workspace_web import (
    patch_project_facility_workspace_response,
)


def test_facility_cockpit_is_appended_once_to_managed_app() -> None:
    original = ApiResponse(200, b"const fieldora=true;", "text/javascript")

    patched = patch_project_facility_workspace_response("/app.js", original)
    repeated = patch_project_facility_workspace_response("/app.js", patched)

    assert repeated.body == patched.body
    text = patched.body.decode("utf-8")
    assert "facility-desktop-cockpit" in text
    assert "Properties" in text
    assert "Metadata" in text
    assert "Map" in text
    assert "Activity" in text
    assert "Rooms & Labs" in text
    assert "Materials / CMDB" in text
    assert "Maps & Floorplans" in text
    assert 'operations.workspace.host' in text
    assert 'host.selectDomain(domain)' in text
    assert 'host.subscribe(()=>renderFacilityCenter())' in text

    # Project workspace ownership moved to Projects/Core.
    assert "project-desktop-cockpit" not in text
    assert "function renderProjectTree()" not in text
    assert 'api("/api/v1/media?limit=500")' not in text
    assert "loadPortfolio=async function()" not in text
    assert 'q("portfolio-list")' not in text
    assert "selectedProject" not in text

    assert "operationsDomain" not in text
    assert "loadOperations=async function()" not in text


def test_facilities_own_projection_dom_instead_of_operations_private_dom() -> None:
    original = ApiResponse(200, b"const fieldora=true;", "text/javascript")
    text = patch_project_facility_workspace_response("/app.js", original).body.decode(
        "utf-8"
    )

    assert 'q("facility-workspace-records")' in text
    assert "data-facility-record-row" in text
    assert 'props.id="facility-inspector-properties"' in text
    assert "facilitySelectedRecordId" in text
    assert 'facilityHost()?.records?.()' in text
    assert 'resolve("operations.workspace.host")' in text
    for private_dom in (
        'q("operations-list")',
        'q("operations-detail")',
        'q("operations-save")',
        "data-operations-id",
    ):
        assert private_dom not in text


def test_project_facility_cockpit_only_patches_successful_app_javascript() -> None:
    response = ApiResponse(200, b"index", "text/html")
    assert patch_project_facility_workspace_response("/", response) is response

    failed = ApiResponse(404, b"missing", "text/javascript")
    assert patch_project_facility_workspace_response("/app.js", failed) is failed
