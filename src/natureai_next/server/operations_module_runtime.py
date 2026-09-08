"""Runtime composition boundary for the nested Operations module."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.web_module_contracts import WebModuleRegistry
from natureai_next.server.web_module_extensions import OPERATIONS_WEB_MODULE_ID

_OPERATIONS_PREFIX = "/api/v1/operations/"
_OPERATIONS_OWNED_DOMAINS = frozenset(
    {
        "assets",
        "maintenance",
        "calibrations",
        "documents",
    }
)


def _operations_owned_path(path: str) -> bool:
    if not path.startswith(_OPERATIONS_PREFIX):
        return False
    domain = path[len(_OPERATIONS_PREFIX) :].split("/", 1)[0]
    return domain in _OPERATIONS_OWNED_DOMAINS


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
        if not self._operations_composed and _operations_owned_path(path):
            return ApiResponse.json(404, {"error": "not_found"})
        return super().dispatch(method, target, headers, body)
