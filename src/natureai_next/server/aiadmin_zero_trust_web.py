"""Deterministic AI Administration zero-trust option projection."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_ZERO_TRUST_OPTION_STATE = b"   option.disabled=!permitted;option.hidden=!permitted;"
_AIADMIN_ATTRIBUTE_OPTION_STATE = (
    b"   const denied=!permitted;"
    b"if(denied){option.setAttribute('disabled','');option.setAttribute('hidden','');}"
    b"else{option.removeAttribute('disabled');option.removeAttribute('hidden');}"
)


def patch_aiadmin_zero_trust_response(target: str, response: ApiResponse) -> ApiResponse:
    """Project AI option authority through explicit cross-engine HTML attributes."""
    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    if (
        _AIADMIN_ATTRIBUTE_OPTION_STATE in response.body
        or _ZERO_TRUST_OPTION_STATE not in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body.replace(
            _ZERO_TRUST_OPTION_STATE,
            _AIADMIN_ATTRIBUTE_OPTION_STATE,
            1,
        ),
        response.content_type,
        response.headers,
    )
