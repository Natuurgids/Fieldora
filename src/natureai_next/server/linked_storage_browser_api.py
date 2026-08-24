"""Browser composition for governed linked-storage Library and Operator surfaces."""

from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi
from natureai_next.server.linked_storage_operator_web import (
    patch_linked_storage_operator_web_response,
)
from natureai_next.server.linked_storage_web import patch_linked_storage_web_response


class LinkedStorageBrowserFieldoraApi(BrowserFunctionalityFieldoraApi):
    """Append linked-storage behavior after the standard browser patches."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        response = patch_linked_storage_web_response(target, response)
        return patch_linked_storage_operator_web_response(target, response)
