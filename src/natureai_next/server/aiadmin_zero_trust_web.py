"""Deterministic AI Administration zero-trust action reconciliation."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_ZERO_TRUST_SHOW_PAGE = (
    b"  baseShowPage(target);if(target!==page&&location.hash===`#${page}`)"
    b"history.replaceState(null,'',`#${target}`);"
)
_AIADMIN_RECONCILED_SHOW_PAGE = (
    b"  baseShowPage(target);if(target==='aiadmin')applyAiAdministrationActions();"
    b"if(target!==page&&location.hash===`#${page}`)"
    b"history.replaceState(null,'',`#${target}`);"
)


def patch_aiadmin_zero_trust_response(target: str, response: ApiResponse) -> ApiResponse:
    """Reapply AI Administration action projection synchronously on page entry."""
    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    if _AIADMIN_RECONCILED_SHOW_PAGE in response.body:
        return response
    if _ZERO_TRUST_SHOW_PAGE not in response.body:
        return response
    return ApiResponse(
        response.status,
        response.body.replace(
            _ZERO_TRUST_SHOW_PAGE,
            _AIADMIN_RECONCILED_SHOW_PAGE,
            1,
        ),
        response.content_type,
        response.headers,
    )
