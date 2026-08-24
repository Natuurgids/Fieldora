"""Browser composition for the governed linked-storage Library surface."""

from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi
from natureai_next.server.linked_storage_web import patch_linked_storage_web_response


class LinkedStorageBrowserFieldoraApi(BrowserFunctionalityFieldoraApi):
    """Append linked-storage Library behavior after the standard browser patches."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_linked_storage_web_response(target, response)
