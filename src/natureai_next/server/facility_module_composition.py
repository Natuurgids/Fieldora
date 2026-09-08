"""Composition-time suppression for the nested Facilities browser projections."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_actions_web import _FACILITY_ACTIONS_PATCH
from natureai_next.server.facility_web_compatibility import _FACILITY_WEB_PATCH

_FACILITY_WORKSPACE_START = b" /* ---- Facility / CMDB cockpit"
_FACILITY_WORKSPACE_END = b"})();"


def suppress_facilities_browser_response(target: str, response: ApiResponse) -> ApiResponse:
    """Remove Facilities-owned browser code when that extension is not composed."""

    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response

    body = response.body.replace(_FACILITY_ACTIONS_PATCH, b"").replace(
        _FACILITY_WEB_PATCH, b""
    )
    start = body.find(_FACILITY_WORKSPACE_START)
    if start >= 0:
        end = body.find(_FACILITY_WORKSPACE_END, start)
        if end >= 0:
            body = body[:start] + body[end:]

    if body == response.body:
        return response
    return ApiResponse(response.status, body, response.content_type, response.headers)
