"""Runtime composition boundary for the nested Facilities module."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.web_module_contracts import WebModuleRegistry
from natureai_next.server.web_module_extensions import FACILITIES_WEB_MODULE_ID

_FACILITY_PLANNING_PREFIX = "/api/v1/facility-planning"
_OPERATIONS_PREFIX = "/api/v1/operations/"
_FACILITY_OPERATION_DOMAINS = frozenset(
    {
        "locations",
        "drawings",
        "storage-conditions",
        "drawing-markers",
        "movements",
    }
)


def _facility_owned_operations_path(path: str) -> bool:
    if not path.startswith(_OPERATIONS_PREFIX):
        return False
    domain = path[len(_OPERATIONS_PREFIX) :].split("/", 1)[0]
    return domain in _FACILITY_OPERATION_DOMAINS


class FacilityModuleCompositionApiMixin:
    """Remove Facilities API/runtime ownership when its module is omitted."""

    _facilities_composed = True

    def configure_web_module_registry(self, registry: WebModuleRegistry) -> None:
        """Apply the same selected registry used by the managed web response."""

        checker = getattr(registry, "is_composed", None)
        self._facilities_composed = (
            True if not callable(checker) else bool(checker(FACILITIES_WEB_MODULE_ID))
        )
        if not self._facilities_composed and hasattr(self, "_facility_platform"):
            self._facility_platform = None

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        path = urlsplit(target).path
        if not self._facilities_composed and (
            path.startswith(_FACILITY_PLANNING_PREFIX)
            or _facility_owned_operations_path(path)
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        return super().dispatch(method, target, headers, body)
