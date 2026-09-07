"""Explicit contracts for independently mounted Fieldora web modules.

The current web client contains compatibility wiring that crosses feature
boundaries. This module provides a deliberately small, framework-independent
contract that can be used while those features are migrated one at a time.

It has no browser or web-framework imports so release tooling and tests can
validate the registry without booting the server or constructing the DOM.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


class WebModuleContractError(ValueError):
    """Raised when a web module registry violates the platform contract."""


@dataclass(frozen=True, slots=True)
class WebModuleSpec:
    """Public metadata owned by one independently mountable web module."""

    module_id: str
    route: str
    label: str
    capability: str | None = None
    owns_actions: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    provides_contracts: tuple[str, ...] = ()
    requires_contracts: tuple[str, ...] = ()
    optional_contracts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        module_id = self.module_id.strip()
        route = normalize_route(self.route)
        label = self.label.strip()
        capability = self.capability.strip() if self.capability else None
        actions = tuple(_normalize_token(value, "action") for value in self.owns_actions)
        dependencies = tuple(
            _normalize_token(value, "dependency") for value in self.dependencies
        )
        provided = tuple(
            _normalize_token(value, "provided contract")
            for value in self.provides_contracts
        )
        required = tuple(
            _normalize_token(value, "required contract")
            for value in self.requires_contracts
        )
        optional = tuple(
            _normalize_token(value, "optional contract")
            for value in self.optional_contracts
        )

        if not module_id:
            raise WebModuleContractError("module_id is required")
        if not label:
            raise WebModuleContractError(f"module {module_id!r} requires a label")
        if not route:
            raise WebModuleContractError(f"module {module_id!r} requires a route")
        if not route.startswith("/"):
            raise WebModuleContractError(
                f"module {module_id!r} route must start with '/': {route!r}"
            )
        if len(set(actions)) != len(actions):
            raise WebModuleContractError(
                f"module {module_id!r} declares duplicate owned actions"
            )
        if len(set(dependencies)) != len(dependencies):
            raise WebModuleContractError(
                f"module {module_id!r} declares duplicate dependencies"
            )
        if len(set(provided)) != len(provided):
            raise WebModuleContractError(
                f"module {module_id!r} declares duplicate provided contracts"
            )
        if len(set(required)) != len(required):
            raise WebModuleContractError(
                f"module {module_id!r} declares duplicate required contracts"
            )
        if len(set(optional)) != len(optional):
            raise WebModuleContractError(
                f"module {module_id!r} declares duplicate optional contracts"
            )
        if module_id in dependencies:
            raise WebModuleContractError(f"module {module_id!r} cannot depend on itself")
        overlap = set(provided).intersection(required)
        if overlap:
            raise WebModuleContractError(
                f"module {module_id!r} cannot require contracts it provides: {sorted(overlap)!r}"
            )
        optional_provider_overlap = set(provided).intersection(optional)
        if optional_provider_overlap:
            raise WebModuleContractError(
                f"module {module_id!r} cannot optionally consume contracts it provides: "
                f"{sorted(optional_provider_overlap)!r}"
            )
        required_optional_overlap = set(required).intersection(optional)
        if required_optional_overlap:
            raise WebModuleContractError(
                f"module {module_id!r} cannot declare contracts as both required and optional: "
                f"{sorted(required_optional_overlap)!r}"
            )

        object.__setattr__(self, "module_id", module_id)
        object.__setattr__(self, "route", route)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "capability", capability)
        object.__setattr__(self, "owns_actions", actions)
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "provides_contracts", provided)
        object.__setattr__(self, "requires_contracts", required)
        object.__setattr__(self, "optional_contracts", optional)


@dataclass(frozen=True, slots=True)
class WebApplicationContractProvider:
    """Non-route platform provider for shared application contracts."""

    provider_id: str
    provides_contracts: tuple[str, ...]

    def __post_init__(self) -> None:
        provider_id = _normalize_token(self.provider_id, "application provider")
        provided = tuple(
            _normalize_token(value, "provided contract")
            for value in self.provides_contracts
        )
        if not provided:
            raise WebModuleContractError(
                f"application provider {provider_id!r} must provide a contract"
            )
        if len(set(provided)) != len(provided):
            raise WebModuleContractError(
                f"application provider {provider_id!r} declares duplicate provided contracts"
            )
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "provides_contracts", provided)


def _normalize_token(value: str, kind: str) -> str:
    token = value.strip()
    if not token:
        raise WebModuleContractError(f"{kind} names may not be blank")
    return token


def normalize_route(route: str) -> str:
    """Return the canonical shell route for a module-owned page."""

    normalized = route.strip().split("#", 1)[0].split("?", 1)[0]
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized


class WebModuleRegistry:
    """Validated ordered registry for modular web-shell ownership."""

    def __init__(
        self,
        specs: Iterable[WebModuleSpec] = (),
        application_providers: Iterable[WebApplicationContractProvider] = (),
    ) -> None:
        self._specs: dict[str, WebModuleSpec] = {}
        self._application_providers: dict[str, WebApplicationContractProvider] = {}
        self._routes: dict[str, str] = {}
        self._actions: dict[str, str] = {}
        self._contracts: dict[str, str] = {}
        for provider in application_providers:
            self.register_application_provider(provider)
        for spec in specs:
            self.register(spec)

    def register_application_provider(
        self, provider: WebApplicationContractProvider
    ) -> None:
        if not isinstance(provider, WebApplicationContractProvider):
            raise WebModuleContractError(
                "registry accepts WebApplicationContractProvider instances only"
            )
        if provider.provider_id in self._application_providers or provider.provider_id in self._specs:
            raise WebModuleContractError(
                f"duplicate provider_id: {provider.provider_id!r}"
            )
        for contract in provider.provides_contracts:
            if contract in self._contracts:
                owner = self._contracts[contract]
                raise WebModuleContractError(
                    f"contract {contract!r} is already provided by {owner!r}"
                )
        self._application_providers[provider.provider_id] = provider
        for contract in provider.provides_contracts:
            self._contracts[contract] = provider.provider_id

    def register(self, spec: WebModuleSpec) -> None:
        if not isinstance(spec, WebModuleSpec):
            raise WebModuleContractError("registry accepts WebModuleSpec instances only")
        if spec.module_id in self._specs or spec.module_id in self._application_providers:
            raise WebModuleContractError(f"duplicate module_id: {spec.module_id!r}")
        if spec.route in self._routes:
            owner = self._routes[spec.route]
            raise WebModuleContractError(
                f"route {spec.route!r} is already owned by module {owner!r}"
            )
        for action in spec.owns_actions:
            if action in self._actions:
                owner = self._actions[action]
                raise WebModuleContractError(
                    f"action {action!r} is already owned by module {owner!r}"
                )
        for contract in spec.provides_contracts:
            if contract in self._contracts:
                owner = self._contracts[contract]
                raise WebModuleContractError(
                    f"contract {contract!r} is already provided by module {owner!r}"
                )
        self._specs[spec.module_id] = spec
        self._routes[spec.route] = spec.module_id
        for action in spec.owns_actions:
            self._actions[action] = spec.module_id
        for contract in spec.provides_contracts:
            self._contracts[contract] = spec.module_id

    def validate_dependencies(self) -> None:
        """Validate only true implementation/load-order module dependencies."""

        missing: dict[str, list[str]] = {}
        for spec in self._specs.values():
            unknown = [dep for dep in spec.dependencies if dep not in self._specs]
            if unknown:
                missing[spec.module_id] = unknown
        if missing:
            raise WebModuleContractError(f"unknown module dependencies: {missing!r}")

    def validate_contracts(self) -> None:
        """Require consumers to bind to a public contract provider."""

        missing: dict[str, list[str]] = {}
        for spec in self._specs.values():
            unknown = [
                contract
                for contract in spec.requires_contracts
                if contract not in self._contracts
            ]
            if unknown:
                missing[spec.module_id] = unknown
        if missing:
            raise WebModuleContractError(f"missing contract providers: {missing!r}")

    def module(self, module_id: str) -> WebModuleSpec:
        try:
            return self._specs[module_id]
        except KeyError as exc:
            raise WebModuleContractError(f"unknown module_id: {module_id!r}") from exc

    def resolve(self, route: str) -> WebModuleSpec | None:
        module_id = self._routes.get(normalize_route(route))
        return self._specs.get(module_id) if module_id else None

    def action_owner(self, action: str) -> WebModuleSpec | None:
        module_id = self._actions.get(action.strip())
        return self._specs.get(module_id) if module_id else None

    def contract_provider(
        self, contract: str
    ) -> WebModuleSpec | WebApplicationContractProvider | None:
        owner_id = self._contracts.get(contract.strip())
        if not owner_id:
            return None
        return self._specs.get(owner_id) or self._application_providers.get(owner_id)

    def visible_specs(self, capabilities: Iterable[str]) -> tuple[WebModuleSpec, ...]:
        """Project discoverability; this is never an authorization decision."""

        allowed = set(capabilities)
        return tuple(
            spec
            for spec in self._specs.values()
            if spec.capability is None or spec.capability in allowed
        )

    def as_mapping(self) -> Mapping[str, WebModuleSpec]:
        return dict(self._specs)

    def application_contract_providers(
        self,
    ) -> Mapping[str, WebApplicationContractProvider]:
        return dict(self._application_providers)


FOUNDATION_APPLICATION_CONTRACT_PROVIDERS: tuple[WebApplicationContractProvider, ...] = (
    WebApplicationContractProvider(
        "application.auth",
        provides_contracts=("auth.current-user",),
    ),
    WebApplicationContractProvider(
        "application.navigation",
        provides_contracts=("navigation.navigate",),
    ),
    WebApplicationContractProvider(
        "application.notifications",
        provides_contracts=("notifications.publish",),
    ),
)


FOUNDATION_WEB_MODULES: tuple[WebModuleSpec, ...] = (
    WebModuleSpec("home.activity", "/home", "Home"),
    WebModuleSpec("library.catalog", "/library", "Library"),
    WebModuleSpec("observations.core", "/observations", "Observations"),
    WebModuleSpec(
        "projects.core",
        "/projects",
        "Projects",
        owns_actions=(
            "projects.create",
            "projects.context.select",
            "projects.scope.select",
            "projects.center.select",
            "projects.progress.refresh",
            "projects.planning.view.select",
            "projects.task.status.move",
            "projects.gantt.inspect",
            "projects.evidence.load",
            "projects.evidence.link",
            "projects.work.inspect",
            "projects.phase.create",
            "projects.task.create",
            "projects.task.edit",
            "projects.milestone.create",
            "projects.subtask.create",
            "projects.sprint.create",
            "projects.allocation.create",
            "projects.details.edit",
            "projects.status.change",
            "projects.archive",
        ),
        provides_contracts=(
            "projects.list.read",
            "projects.context.select",
            "projects.toolbar.extend",
            "projects.selected-record.select",
            "projects.work-data.service",
            "projects.evidence.service",
        ),
        requires_contracts=(
            "auth.current-user",
            "navigation.navigate",
            "notifications.publish",
        ),
    ),
    WebModuleSpec(
        "portfolio",
        "/portfolio",
        "Portfolio",
        owns_actions=(
            "portfolio.view.select",
            "portfolio.scope.select",
            "portfolio.project.open",
        ),
        requires_contracts=(
            "auth.current-user",
            "navigation.navigate",
            "notifications.publish",
            "projects.list.read",
            "projects.context.select",
        ),
    ),
    WebModuleSpec(
        "capacity",
        "/capacity",
        "Capacity",
        owns_actions=(
            "capacity.project.open",
            "capacity.project.allocations.view",
            "capacity.project.allocations.create",
            "capacity.availability.view",
            "capacity.schedule.assign",
            "capacity.absence.register",
            "capacity.obligation.create",
        ),
        requires_contracts=(
            "navigation.navigate",
            "notifications.publish",
            "projects.context.select",
            "projects.toolbar.extend",
        ),
    ),
    WebModuleSpec(
        "research.dossiers",
        "/research",
        "Research",
        owns_actions=(
            "research.project.open",
            "research.project.records.view",
        ),
        requires_contracts=(
            "navigation.navigate",
            "notifications.publish",
            "projects.context.select",
            "projects.toolbar.extend",
        ),
    ),
    WebModuleSpec(
        "dossiers.workspace",
        "/dossiers",
        "Dossiers",
        owns_actions=(
            "dossiers.workspace.view",
            "dossiers.create",
            "dossiers.review.create",
        ),
        requires_contracts=(
            "auth.current-user",
            "notifications.publish",
            "projects.context.select",
        ),
    ),
    WebModuleSpec("knowledge.center", "/knowledge", "Knowledge & AI"),
    WebModuleSpec(
        "admin.shell",
        "/administration",
        "Administration",
        capability="administration.view",
    ),
)


def foundation_registry() -> WebModuleRegistry:
    registry = WebModuleRegistry(
        FOUNDATION_WEB_MODULES,
        application_providers=FOUNDATION_APPLICATION_CONTRACT_PROVIDERS,
    )
    registry.validate_dependencies()
    registry.validate_contracts()
    return registry
