"""Central navigation contracts for the Fieldora desktop.

This module intentionally has no Qt imports so release tooling can validate the
workspace and route inventory even when PySide6 is unavailable.  Runtime-only
page integrations are imported lazily after the structural contract succeeds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class WorkspaceSpec:
    name: str
    factory_name: str


V5_WORKSPACE_SPECS: tuple[WorkspaceSpec, ...] = (
    WorkspaceSpec("Home", "Home"),
    WorkspaceSpec("Library Overview", "Library"),
    WorkspaceSpec("Observations Overview", "Observations"),
    WorkspaceSpec("Research Overview", "Research"),
    WorkspaceSpec("Measurements & Protocols", "MeasurementsSampling"),
    WorkspaceSpec("Knowledge & AI Overview", "Knowledge"),
    WorkspaceSpec("AI Chat & MCP", "AIChatWorkspace"),
    WorkspaceSpec("AI Platform Administration", "AIPlatformAdministration"),
    WorkspaceSpec("Administration Overview", "Administration"),
    WorkspaceSpec("Research Reference Data", "ResearchReferenceData"),
    WorkspaceSpec("Administration Governance", "AdministrationGovernance"),
    WorkspaceSpec("Platform Parity", "PlatformParity"),
    WorkspaceSpec("Asset & Equipment Operations", "AssetEquipmentOperations"),
    WorkspaceSpec("Local Profiles", "LocalProfiles"),
    WorkspaceSpec("Help & Guides", "Help"),
)

# Context routes are resolved by MainWindow._handle_v5_context_route.  Prefixes
# include their separator so accidental near-matches are rejected.
CONTEXT_ROUTE_PREFIXES: tuple[str, ...] = (
    "__project_open__:",
    "__project_measurements__:",
    "__project_surveys__:",
    "__project_quality__:",
    "__project_map__:",
    "__asset_open__:",
    "__asset_collection__:",
    "__asset_observation__:",
    "__asset_dossier__:",
    "__observation_open__:",
    "__help_topic__:",
    "__help_search__:",
)

CONTEXT_ROUTES: frozenset[str] = frozenset(
    {
        "__help__", "__manuals__", "__shortcuts__", "__backup__", "__restore__",
        "__observation_new__",
        "__asset_collection__", "__asset_export__", "__asset_open__",
        "__observation_evidence__", "__observation_map__", "__observation_record__",
        "__project_open__", "__project_map__", "__project_surveys__",
        "__project_measurements__", "__project_quality__",
    }
)

ROUTE_ALIASES: Mapping[str, str] = {
    "AI Review": "Knowledge Base",
    "Taxonomy": "Knowledge Base",
}


def workspace_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in V5_WORKSPACE_SPECS)


def normalize_route(route: str) -> str:
    return ROUTE_ALIASES.get(route, route)


def is_context_route(route: str) -> bool:
    return route in CONTEXT_ROUTES or any(route.startswith(prefix) for prefix in CONTEXT_ROUTE_PREFIXES)


def is_supported_route(route: str, workspaces: Iterable[str]) -> bool:
    normalized = normalize_route(route)
    return normalized in set(workspaces) or is_context_route(route)


def _apply_runtime_page_integrations(pages: Mapping[str, object]) -> None:
    """Attach optional Qt integrations only to real V5 runtime page objects.

    Keeping this lazy preserves the import-free navigation contract for release
    tooling while allowing the large legacy V5 desktop module to be extended by
    focused, testable components.
    """
    operations = pages.get("Asset & Equipment Operations")
    if operations is None:
        return
    page_type = type(operations)
    if page_type.__module__ != "natureai_next.ui.qt.v5_desktop" or page_type.__name__ != "AssetEquipmentOperations":
        return
    from natureai_next.ui.qt.facility_operations_integration import (
        integrate_asset_equipment_operations,
    )

    integrate_asset_equipment_operations(operations)


def validate_page_mapping(pages: Mapping[str, object]) -> None:
    expected = workspace_names()
    actual = tuple(pages)
    if actual != expected:
        missing = [name for name in expected if name not in pages]
        extra = [name for name in actual if name not in expected]
        raise RuntimeError(
            "V5 workspace registry mismatch: "
            f"missing={missing or 'none'}, extra={extra or 'none'}, order={actual!r}"
        )
    duplicate_objects: dict[int, list[str]] = {}
    for name, page in pages.items():
        duplicate_objects.setdefault(id(page), []).append(name)
        if page is None:
            raise RuntimeError(f"V5 workspace factory returned None for {name}")
        if not hasattr(page, "route_requested"):
            raise RuntimeError(f"V5 workspace {name} does not expose route_requested")
        if not callable(getattr(page, "refresh", None)):
            raise RuntimeError(f"V5 workspace {name} does not expose refresh()")
    duplicates = [names for names in duplicate_objects.values() if len(names) > 1]
    if duplicates:
        raise RuntimeError(f"V5 workspace registry reuses page instances: {duplicates!r}")
    _apply_runtime_page_integrations(pages)
