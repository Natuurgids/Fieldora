from __future__ import annotations

from natureai_next.server.operations_module_ownership import (
    FACILITIES_OPERATIONS_API_DOMAINS,
    FACILITIES_SCIENCE_ROUTES,
    OPERATIONS_API_DOMAINS,
    OPERATIONS_API_PREFIX,
    OPERATIONS_SCIENCE_ROUTES,
    SHARED_OPERATIONS_SCIENCE_ROUTES,
    operations_api_domain,
    operations_api_owner,
)
from natureai_next.server.web_module_extensions import (
    FACILITIES_WEB_MODULE_ID,
    OPERATIONS_WEB_MODULE_ID,
)


def test_shared_operations_api_domains_have_single_module_owner() -> None:
    assert OPERATIONS_API_DOMAINS.isdisjoint(FACILITIES_OPERATIONS_API_DOMAINS)

    for domain in OPERATIONS_API_DOMAINS:
        path = f"/api/v1/operations/{domain}/example"
        assert operations_api_domain(path) == domain
        assert operations_api_owner(path) == OPERATIONS_WEB_MODULE_ID

    for domain in FACILITIES_OPERATIONS_API_DOMAINS:
        path = f"/api/v1/operations/{domain}/example"
        assert operations_api_domain(path) == domain
        assert operations_api_owner(path) == FACILITIES_WEB_MODULE_ID


def test_shared_operations_science_routes_are_owned_and_complete() -> None:
    assert set(OPERATIONS_SCIENCE_ROUTES).isdisjoint(FACILITIES_SCIENCE_ROUTES)
    assert SHARED_OPERATIONS_SCIENCE_ROUTES == {
        **OPERATIONS_SCIENCE_ROUTES,
        **FACILITIES_SCIENCE_ROUTES,
    }
    assert OPERATIONS_API_DOMAINS == frozenset(
        path.removeprefix(OPERATIONS_API_PREFIX) for path in OPERATIONS_SCIENCE_ROUTES
    )
    assert FACILITIES_OPERATIONS_API_DOMAINS == frozenset(
        path.removeprefix(OPERATIONS_API_PREFIX) for path in FACILITIES_SCIENCE_ROUTES
    )

    for path in OPERATIONS_SCIENCE_ROUTES:
        assert path.startswith(OPERATIONS_API_PREFIX)
        assert operations_api_owner(path) == OPERATIONS_WEB_MODULE_ID
    for path in FACILITIES_SCIENCE_ROUTES:
        assert path.startswith(OPERATIONS_API_PREFIX)
        assert operations_api_owner(path) == FACILITIES_WEB_MODULE_ID


def test_shared_operations_science_route_contract_matches_legacy_api_surface() -> None:
    assert SHARED_OPERATIONS_SCIENCE_ROUTES == {
        "/api/v1/operations/assets": (
            "ops_equipment_assets",
            "operations_asset",
        ),
        "/api/v1/operations/maintenance": (
            "ops_maintenance_events",
            "operations_maintenance",
        ),
        "/api/v1/operations/calibrations": (
            "ops_calibration_events",
            "operations_calibration",
        ),
        "/api/v1/operations/documents": (
            "ops_asset_documents",
            "operations_document",
        ),
        "/api/v1/operations/locations": (
            "ops_locations",
            "operations_location",
        ),
        "/api/v1/operations/drawings": (
            "ops_building_drawings",
            "operations_drawing",
        ),
        "/api/v1/operations/storage-conditions": (
            "ops_storage_conditions",
            "operations_storage_condition",
        ),
        "/api/v1/operations/drawing-markers": (
            "ops_drawing_markers",
            "operations_drawing_marker",
        ),
        "/api/v1/operations/movements": (
            "ops_asset_movements",
            "operations_movement",
        ),
    }


def test_shared_operations_api_classifier_does_not_claim_unknown_paths() -> None:
    assert operations_api_domain("/api/v1/projects") is None
    assert operations_api_domain("/api/v1/operations/") is None
    assert operations_api_owner("/api/v1/operations/unknown") is None


def test_operations_browser_omission_patches_do_not_claim_administration_dom() -> None:
    from natureai_next.server import operations_module_composition as composition

    for patch in (
        composition._OPERATIONS_WITH_FACILITIES_PATCH,
        composition._OPERATIONS_WITHOUT_FACILITIES_PATCH,
    ):
        script = patch.decode("utf-8")
        assert "administration-nav-group" not in script
        assert "administration-nav-group-label" not in script


def test_facilities_offline_maps_patch_uses_workspace_host_refresh_contract() -> None:
    from natureai_next.server.offline_maps_web import _OFFLINE_MAPS_WEB_PATCH

    script = _OFFLINE_MAPS_WEB_PATCH.decode("utf-8")
    assert "baseLoadOperations=loadOperations" not in script
    assert "loadOperations=async function" not in script
    assert "operations.workspace.host" in script
    assert "host.subscribe(" in script
    assert "fieldora:contracts-ready" in script
    assert 'getElementById("operations-refresh")' not in script
    assert 'querySelectorAll(\'.nav[data-page="operations"]\')' not in script
