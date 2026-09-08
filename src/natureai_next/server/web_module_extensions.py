"""Explicit non-route composition identities for nested web modules."""

from __future__ import annotations

from dataclasses import dataclass

from natureai_next.server.web_module_contracts import WebModuleContractError, normalize_route


@dataclass(frozen=True, slots=True)
class WebModuleExtensionSpec:
    """A composed module that extends a host surface without owning that route."""

    module_id: str
    label: str
    host_route: str

    def __post_init__(self) -> None:
        module_id = self.module_id.strip()
        label = self.label.strip()
        host_route = normalize_route(self.host_route)
        if not module_id:
            raise WebModuleContractError("extension module_id is required")
        if not label:
            raise WebModuleContractError(f"extension module {module_id!r} requires a label")
        if not host_route or not host_route.startswith("/"):
            raise WebModuleContractError(
                f"extension module {module_id!r} host route must start with '/': {host_route!r}"
            )
        object.__setattr__(self, "module_id", module_id)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "host_route", host_route)


OPERATIONS_WEB_MODULE_ID = "operations"
FACILITIES_WEB_MODULE_ID = "facilities"

FOUNDATION_WEB_MODULE_EXTENSIONS: tuple[WebModuleExtensionSpec, ...] = (
    WebModuleExtensionSpec(
        OPERATIONS_WEB_MODULE_ID,
        "Operations",
        "/operations",
    ),
    WebModuleExtensionSpec(
        FACILITIES_WEB_MODULE_ID,
        "Facilities",
        "/operations",
    ),
)
