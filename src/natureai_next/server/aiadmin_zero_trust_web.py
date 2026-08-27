"""Deterministic AI Administration zero-trust action reconciliation."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_ZERO_TRUST_OPTION_STATE = b"   option.disabled=!permitted;option.hidden=!permitted;"
_AIADMIN_ATTRIBUTE_OPTION_STATE = (
    b"   const denied=!permitted;"
    b"if(option.disabled!==denied)option.disabled=denied;"
    b"if(option.hidden!==denied)option.hidden=denied;"
)
_ZERO_TRUST_AI_LISTENER = (
    b" const aiRecordType=document.getElementById('ai-record-type');\n"
    b" if(aiRecordType)aiRecordType.addEventListener('change',applyAiAdministrationActions);"
)
_AIADMIN_RECONCILED_AI_LISTENER = (
    b" const aiRecordType=document.getElementById('ai-record-type');\n"
    b" if(aiRecordType){\n"
    b"  aiRecordType.addEventListener('change',applyAiAdministrationActions);\n"
    b"  const aiOptionObserver=new MutationObserver(()=>applyAiAdministrationActions());\n"
    b"  aiOptionObserver.observe(aiRecordType,{subtree:true,attributes:true,attributeFilter:['disabled','hidden']});\n"
    b" }"
)


def patch_aiadmin_zero_trust_response(target: str, response: ApiResponse) -> ApiResponse:
    """Keep AI Administration option authorization stable across async rendering."""
    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    body = response.body
    if _AIADMIN_ATTRIBUTE_OPTION_STATE not in body and _ZERO_TRUST_OPTION_STATE in body:
        body = body.replace(
            _ZERO_TRUST_OPTION_STATE,
            _AIADMIN_ATTRIBUTE_OPTION_STATE,
            1,
        )
    if _AIADMIN_RECONCILED_AI_LISTENER not in body and _ZERO_TRUST_AI_LISTENER in body:
        body = body.replace(
            _ZERO_TRUST_AI_LISTENER,
            _AIADMIN_RECONCILED_AI_LISTENER,
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
