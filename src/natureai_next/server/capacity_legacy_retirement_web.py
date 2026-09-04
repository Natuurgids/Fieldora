"""Retire legacy Capacity compatibility wiring after both modular owners exist."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_ALLOCATION_OWNER_MARKER = b"WEB-CAPACITY-MODULE"
_AVAILABILITY_OWNER_MARKER = b"WEB-CAPACITY-AVAILABILITY-MODULE"
_LEGACY_CAPACITY_LOAD_START = b"async function loadCapacity(){"
_LEGACY_CAPACITY_LOAD_END = b"async function loadDossierWorkspace(){"
_LEGACY_CAPACITY_SHOWPAGE_LOAD = b'if(name==="capacity")loadCapacity();'
_LEGACY_CAPACITY_REFRESH_WIRING = b'q("capacity-refresh").onclick=loadCapacity;'
_LEGACY_CAPACITY_PROJECT_OPTIONS = b'"work-project","capacity-project","dossier-project"'
_MANAGED_PROJECT_OPTIONS = b'"work-project","dossier-project"'


def _retire_legacy_capacity_load(body: bytes) -> bytes:
    """Remove only legacy Capacity wiring when both modular owners are present."""

    if (
        _ALLOCATION_OWNER_MARKER not in body
        or _AVAILABILITY_OWNER_MARKER not in body
    ):
        return body
    start = body.find(_LEGACY_CAPACITY_LOAD_START)
    end = body.find(_LEGACY_CAPACITY_LOAD_END, start) if start >= 0 else -1
    if start >= 0 and end >= 0:
        body = body[:start] + body[end:]
    body = body.replace(_LEGACY_CAPACITY_SHOWPAGE_LOAD, b"", 1)
    body = body.replace(_LEGACY_CAPACITY_REFRESH_WIRING, b"", 1)
    return body.replace(_LEGACY_CAPACITY_PROJECT_OPTIONS, _MANAGED_PROJECT_OPTIONS, 1)


def patch_capacity_legacy_retirement_response(
    target: str, response: ApiResponse
) -> ApiResponse:
    """Retire competing legacy Capacity wiring after modular composition."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    body = _retire_legacy_capacity_load(response.body)
    if body == response.body:
        return response
    return ApiResponse(response.status, body, response.content_type, response.headers)


class CapacityLegacyRetirementWebApiMixin:
    """Finalize Capacity browser ownership after both modular owners compose."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_capacity_legacy_retirement_response(target, response)
