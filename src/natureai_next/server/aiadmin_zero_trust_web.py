"""Deterministic AI Administration zero-trust action reconciliation."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_ZERO_TRUST_OPTION_STATE = b"   option.disabled=!permitted;option.hidden=!permitted;"
_AIADMIN_ATTRIBUTE_OPTION_STATE = (
    b"   option.toggleAttribute('disabled',!permitted);"
    b"option.toggleAttribute('hidden',!permitted);"
)
_ZERO_TRUST_SHOW_PAGE = (
    b"  baseShowPage(target);if(target!==page&&location.hash===`#${page}`)"
    b"history.replaceState(null,'',`#${target}`);"
)
_AIADMIN_RECONCILED_SHOW_PAGE = (
    b"  baseShowPage(target);if(target==='aiadmin')applyAiAdministrationActions();"
    b"if(target!==page&&location.hash===`#${page}`)"
    b"history.replaceState(null,'',`#${target}`);"
)
_ZERO_TRUST_BASE_API = b" const baseApi=api;"
_AIADMIN_RECONCILED_BASE_API = (
    b" const baseLoadAIAdministration=loadAIAdministration;"
    b" loadAIAdministration=async function(){"
    b"try{return await baseLoadAIAdministration();}"
    b"finally{applyAiAdministrationActions();}"
    b"};"
    b" const baseApi=api;"
)


def patch_aiadmin_zero_trust_response(target: str, response: ApiResponse) -> ApiResponse:
    """Project AI Administration permissions as stable browser-native state."""
    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    body = response.body
    if _AIADMIN_ATTRIBUTE_OPTION_STATE not in body and _ZERO_TRUST_OPTION_STATE in body:
        body = body.replace(
            _ZERO_TRUST_OPTION_STATE,
            _AIADMIN_ATTRIBUTE_OPTION_STATE,
            1,
        )
    if _AIADMIN_RECONCILED_SHOW_PAGE not in body and _ZERO_TRUST_SHOW_PAGE in body:
        body = body.replace(
            _ZERO_TRUST_SHOW_PAGE,
            _AIADMIN_RECONCILED_SHOW_PAGE,
            1,
        )
    if _AIADMIN_RECONCILED_BASE_API not in body and _ZERO_TRUST_BASE_API in body:
        body = body.replace(
            _ZERO_TRUST_BASE_API,
            _AIADMIN_RECONCILED_BASE_API,
            1,
        )
    if body == response.body:
        return response
    return ApiResponse(
        response.status,
        body,
        response.content_type,
        response.headers,
    )
