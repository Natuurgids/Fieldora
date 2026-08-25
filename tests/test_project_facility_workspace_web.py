from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_facility_workspace_web import (
    patch_project_facility_workspace_response,
)


def test_project_and_facility_cockpit_is_appended_once_to_managed_app() -> None:
    original = ApiResponse(200, b"const fieldora=true;", "text/javascript")

    patched = patch_project_facility_workspace_response("/app.js", original)
    repeated = patch_project_facility_workspace_response("/app.js", patched)

    assert repeated.body == patched.body
    text = patched.body.decode("utf-8")
    assert "project-desktop-cockpit" in text
    assert "facility-desktop-cockpit" in text
    assert "Properties" in text
    assert "Metadata" in text
    assert "Map" in text
    assert "Activity" in text
    assert "Rooms & Labs" in text
    assert "Materials / CMDB" in text
    assert "Maps & Floorplans" in text
    assert 'operationsDomain=({buildings:"locations",rooms:"locations"' in text
    assert 'api("/api/v1/media?limit=500")' in text
    assert "loadPortfolio=async function()" in text
    assert "loadOperations=async function()" in text


def test_project_facility_cockpit_only_patches_successful_app_javascript() -> None:
    response = ApiResponse(200, b"index", "text/html")
    assert patch_project_facility_workspace_response("/", response) is response

    failed = ApiResponse(404, b"missing", "text/javascript")
    assert patch_project_facility_workspace_response("/app.js", failed) is failed
