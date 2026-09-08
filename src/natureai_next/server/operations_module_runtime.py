"""Runtime composition boundary for the nested Operations module."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.operations_module_ownership import operations_api_owner
from natureai_next.server.web_module_contracts import WebModuleRegistry
from natureai_next.server.web_module_extensions import OPERATIONS_WEB_MODULE_ID


class OperationsModuleCompositionApiMixin:
    """Remove Operations API ownership when its module is omitted."""

    _operations_composed = True

    def configure_web_module_registry(self, registry: WebModuleRegistry) -> None:
        """Apply composition after any later mixin has configured its own state."""

        configure_parent = getattr(super(), "configure_web_module_registry", None)
        if callable(configure_parent):
            configure_parent(registry)
        checker = getattr(registry, "is_composed", None)
        self._operations_composed = (
            True if not callable(checker) else bool(checker(OPERATIONS_WEB_MODULE_ID))
        )

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        path = urlsplit(target).path
        if (
            not self._operations_composed
            and operations_api_owner(path) == OPERATIONS_WEB_MODULE_ID
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        return super().dispatch(method, target, headers, body)
