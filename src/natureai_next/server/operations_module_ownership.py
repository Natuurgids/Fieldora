"""Canonical API ownership for the shared Operations workspace namespace."""

from __future__ import annotations

from natureai_next.server.web_module_extensions import (
    FACILITIES_WEB_MODULE_ID,
    OPERATIONS_WEB_MODULE_ID,
)

OPERATIONS_API_PREFIX = "/api/v1/operations/"
OPERATIONS_API_DOMAINS = frozenset(
    {
        "assets",
        "maintenance",
        "calibrations",
        "documents",
    }
)
FACILITIES_OPERATIONS_API_DOMAINS = frozenset(
    {
        "locations",
        "drawings",
        "storage-conditions",
        "drawing-markers",
        "movements",
    }
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
