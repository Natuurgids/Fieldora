"""Final managed-browser cleanup for WEB-040 visible-control auditing.

This seam runs after the feature/workspace patches. It removes legacy controls that
remain visible but no longer own an action contract in the final desktop-aligned UI.
Workspace-specific action expansion remains in WEB-041 through WEB-046.
"""

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_VISIBLE_CONTROL_AUDIT_PATCH = bytes(
    r"""

/* WEB-040: a visible control must have a real action contract. */
(()=>{
 if(window.__fieldoraVisibleControlAuditWired)return;
 window.__fieldoraVisibleControlAuditWired=true;

 /* The original Knowledge shell shipped two anonymous pseudo-tabs (Review queue /
    Accepted knowledge). The desktop-aligned workflow now owns navigation through
    Review knowledge / Add identification, while proposal state and explicit
    Accept/Reject/Defer actions are rendered by the governed Knowledge seam. Leaving
    the old pair visible creates two buttons with no event/action contract. */
 const legacyKnowledgeTabs=document.querySelector("#knowledge-review-panel > section.card > .tabs");
 if(legacyKnowledgeTabs)legacyKnowledgeTabs.remove();
})();
""",
    "utf-8",
)


def patch_visible_control_audit_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _VISIBLE_CONTROL_AUDIT_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _VISIBLE_CONTROL_AUDIT_PATCH,
        response.content_type,
        response.headers,
    )
