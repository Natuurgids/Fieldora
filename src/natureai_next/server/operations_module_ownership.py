"""Canonical API ownership for the shared Operations workspace namespace."""

from __future__ import annotations

from natureai_next.server.web_module_extensions import (
    FACILITIES_WEB_MODULE_ID,
    OPERATIONS_WEB_MODULE_ID,
)

OPERATIONS_API_PREFIX = "/api/v1/operations/"

OPERATIONS_SCIENCE_ROUTES: dict[str, tuple[str, str]] = {
    f"{OPERATIONS_API_PREFIX}assets": (
        "ops_equipment_assets",
        "operations_asset",
    ),
    f"{OPERATIONS_API_PREFIX}maintenance": (
        "ops_maintenance_events",
        "operations_maintenance",
    ),
    f"{OPERATIONS_API_PREFIX}calibrations": (
        "ops_calibration_events",
        "operations_calibration",
    ),
    f"{OPERATIONS_API_PREFIX}documents": (
        "ops_asset_documents",
        "operations_document",
    ),
}
FACILITIES_SCIENCE_ROUTES: dict[str, tuple[str, str]] = {
    f"{OPERATIONS_API_PREFIX}locations": (
        "ops_locations",
        "operations_location",
    ),
    f"{OPERATIONS_API_PREFIX}drawings": (
        "ops_building_drawings",
        "operations_drawing",
    ),
    f"{OPERATIONS_API_PREFIX}storage-conditions": (
        "ops_storage_conditions",
        "operations_storage_condition",
    ),
    f"{OPERATIONS_API_PREFIX}drawing-markers": (
        "ops_drawing_markers",
        "operations_drawing_marker",
    ),
    f"{OPERATIONS_API_PREFIX}movements": (
        "ops_asset_movements",
        "operations_movement",
    ),
}
SHARED_OPERATIONS_SCIENCE_ROUTES: dict[str, tuple[str, str]] = {
    **OPERATIONS_SCIENCE_ROUTES,
    **FACILITIES_SCIENCE_ROUTES,
}

OPERATIONS_API_DOMAINS = frozenset(
    path.removeprefix(OPERATIONS_API_PREFIX) for path in OPERATIONS_SCIENCE_ROUTES
)
FACILITIES_OPERATIONS_API_DOMAINS = frozenset(
    path.removeprefix(OPERATIONS_API_PREFIX) for path in FACILITIES_SCIENCE_ROUTES
)


def operations_api_domain(path: str) -> str | None:
    """Return the first domain segment inside the shared Operations API namespace."""

    if not path.startswith(OPERATIONS_API_PREFIX):
        return None
    domain = path[len(OPERATIONS_API_PREFIX) :].split("/", 1)[0]
    return domain or None


def operations_api_owner(path: str) -> str | None:
    """Return the composed module that owns a known shared-namespace API path."""

    domain = operations_api_domain(path)
    if domain in OPERATIONS_API_DOMAINS:
        return OPERATIONS_WEB_MODULE_ID
    if domain in FACILITIES_OPERATIONS_API_DOMAINS:
        return FACILITIES_WEB_MODULE_ID
    return None
