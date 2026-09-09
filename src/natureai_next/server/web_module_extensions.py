"""Explicit non-route composition identities for nested web modules."""

from __future__ import annotations

from dataclasses import dataclass

from natureai_next.server.web_module_contracts import WebModuleContractError, normalize_route


def _normalize_contracts(values: tuple[str, ...], kind: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if any(not value for value in normalized):
        raise WebModuleContractError(f"extension {kind} names may not be blank")
    if len(set(normalized)) != len(normalized):
        raise WebModuleContractError(f"extension declares duplicate {kind}")
    return normalized


@dataclass(frozen=True, slots=True)
class WebModuleExtensionSpec:
    """A composed module that extends a host surface without owning that route."""

    module_id: str
    label: str
    host_route: str
    provides_contracts: tuple[str, ...] = ()
    requires_contracts: tuple[str, ...] = ()
    optional_contracts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        module_id = self.module_id.strip()
        label = self.label.strip()
        host_route = normalize_route(self.host_route)
        provided = _normalize_contracts(self.provides_contracts, "provided contracts")
        required = _normalize_contracts(self.requires_contracts, "required contracts")
        optional = _normalize_contracts(self.optional_contracts, "optional contracts")
        if not module_id:
            raise WebModuleContractError("extension module_id is required")
        if not label:
            raise WebModuleContractError(f"extension module {module_id!r} requires a label")
        if not host_route or not host_route.startswith("/"):
            raise WebModuleContractError(
                f"extension module {module_id!r} host route must start with '/': {host_route!r}"
            )
        if set(provided).intersection(required):
            raise WebModuleContractError(
                f"extension module {module_id!r} cannot require contracts it provides"
            )
        if set(provided).intersection(optional):
            raise WebModuleContractError(
                f"extension module {module_id!r} cannot optionally consume contracts it provides"
            )
        if set(required).intersection(optional):
            raise WebModuleContractError(
                f"extension module {module_id!r} cannot declare contracts as both required and optional"
            )
        object.__setattr__(self, "module_id", module_id)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "host_route", host_route)
        object.__setattr__(self, "provides_contracts", provided)
        object.__setattr__(self, "requires_contracts", required)
        object.__setattr__(self, "optional_contracts", optional)


OPERATIONS_WEB_MODULE_ID = "operations"
FACILITIES_WEB_MODULE_ID = "facilities"

FOUNDATION_WEB_MODULE_EXTENSIONS: tuple[WebModuleExtensionSpec, ...] = (
    WebModuleExtensionSpec(
        OPERATIONS_WEB_MODULE_ID,
        "Operations",
        "/operations",
        requires_contracts=("operations.workspace.host",),
    ),
    WebModuleExtensionSpec(
        FACILITIES_WEB_MODULE_ID,
        "Facilities",
        "/operations",
        requires_contracts=("operations.workspace.host",),
    ),
)
