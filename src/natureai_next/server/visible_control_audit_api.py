"""Final response wrapper for WEB-040 managed-browser visible-control auditing."""

from natureai_next.server.api import ApiResponse
from natureai_next.server.visible_control_audit_web import (
    patch_visible_control_audit_response,
)


class VisibleControlAuditApiMixin:
    """Apply final visible-control cleanup after all other browser patches."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_visible_control_audit_response(target, response)
