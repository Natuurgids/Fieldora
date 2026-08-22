"""Authoritative cross-platform feature and parity registry.

The registry is intentionally UI-independent.  Windows and Linux desktop use
exactly the same Qt workspaces and application services; the server exposes the
same registry over its API and web administration surface.  A feature may only
be marked certified after platform-specific evidence is recorded.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Iterable


class Platform(StrEnum):
    WINDOWS_DESKTOP = "windows_desktop"
    LINUX_DESKTOP = "linux_desktop"
    SERVER = "server"


class FeatureStatus(StrEnum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    PLATFORM_SPECIFIC = "platform_specific"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True, slots=True)
class PlatformImplementation:
    platform: Platform
    status: FeatureStatus
    surface: str
    evidence_required: str
    certified: bool = False


@dataclass(frozen=True, slots=True)
class PlatformFeature:
    feature_id: str
    module: str
    name: str
    description: str
    permission: str
    implementations: tuple[PlatformImplementation, ...]

    def as_dict(self) -> dict:
        value = asdict(self)
        value["implementations"] = [
            {**asdict(item), "platform": item.platform.value, "status": item.status.value}
            for item in self.implementations
        ]
        return value


def _desktop(surface: str) -> tuple[PlatformImplementation, PlatformImplementation]:
    evidence = "Launch workspace, execute representative CRUD/action flow, verify audit and restart persistence."
    return (
        PlatformImplementation(Platform.WINDOWS_DESKTOP, FeatureStatus.IMPLEMENTED, surface, evidence),
        PlatformImplementation(Platform.LINUX_DESKTOP, FeatureStatus.IMPLEMENTED, surface, evidence),
    )


def _server(status: FeatureStatus, surface: str, evidence: str | None = None) -> PlatformImplementation:
    return PlatformImplementation(
        Platform.SERVER,
        status,
        surface,
        evidence or "Exercise server UI and API with administrator and restricted-user accounts.",
    )


def _feature(fid: str, module: str, name: str, surface: str, server_status: FeatureStatus,
             server_surface: str, permission: str = "view", description: str = "") -> PlatformFeature:
    return PlatformFeature(
        fid, module, name, description or name, permission,
        (*_desktop(surface), _server(server_status, server_surface)),
    )


FEATURES: tuple[PlatformFeature, ...] = (
    _feature("core.login", "Platform", "Authentication and profiles", "Login / Local Profiles", FeatureStatus.IMPLEMENTED, "Session API / OIDC login", "authenticate"),
    _feature("core.access", "Governance", "RBAC, ABAC, PBAC and access matrices", "Administration Governance", FeatureStatus.IMPLEMENTED, "Policy APIs / contracts", "administration"),
    _feature("project.workspace", "Projects", "Projects, phases, tasks and subtasks", "Project Workspace", FeatureStatus.IMPLEMENTED, "Projects, phases, tasks and subtasks web workspace and APIs", "project.view"),
    _feature("project.portfolio", "Projects", "Portfolio and My Work", "Portfolio & My Work", FeatureStatus.IMPLEMENTED, "Portfolio and My Work web workspace and APIs", "project.view"),
    _feature("project.capacity", "Projects", "Schedules, absence, allocations and workload", "Availability / Workload", FeatureStatus.IMPLEMENTED, "Schedules, absences, obligations, allocations and workload web workspace", "project.manage"),
    _feature("research.operations", "Research", "Specimens, protocols, surveys, samples and laboratory", "Measurements & Protocols", FeatureStatus.IMPLEMENTED, "Research operations web workspace and APIs", "research.view"),
    _feature("observations.review", "Observations", "Observation review and bulk decisions", "Observations Overview", FeatureStatus.IMPLEMENTED, "Observation review and bulk-decision web workspace", "observation.review"),
    _feature("dossiers.workspace", "Dossiers", "Independent, project and master dossiers", "Dossiers", FeatureStatus.IMPLEMENTED, "Dossier hierarchy, review and ownership web workspace", "dossier.view"),
    _feature("library.assets", "Library", "Unified multimedia asset catalogue", "Library Overview", FeatureStatus.IMPLEMENTED, "Library media gallery and governed download", "asset.view"),
    _feature("ai.platform", "AI", "Provider-neutral offline AI and MCP", "AI Chat & MCP / AI Platform Administration", FeatureStatus.IMPLEMENTED, "AI provider, model and MCP administration web workspace", "ai.use"),
    _feature("admin.reference_data", "Administration", "Reference data", "Research Reference Data", FeatureStatus.IMPLEMENTED, "Reference-data administration web workspace and API", "reference_data.view"),
    _feature("admin.audit", "Administration", "Audit and governance evidence", "Administration Governance", FeatureStatus.IMPLEMENTED, "Audit API and administration audit list", "audit.view"),
    _feature("connectors.registry", "Connectors", "Connector registry and health", "Integrations / Resource Components", FeatureStatus.IMPLEMENTED, "Connector registry, capabilities and health web workspace", "connector.view"),
    _feature("staging.intake", "Staging", "Governed staged ingestion", "Library governed import", FeatureStatus.IMPLEMENTED, "Staged-submission API and web upload", "staging.create"),
    _feature("operations.assets", "Operations", "Assets, equipment, maintenance, calibration, facilities and storage", "Asset & Equipment Operations", FeatureStatus.IMPLEMENTED, "Operations web workspace, APIs and PostgreSQL schema", "operations.view"),
    _feature("help.offline", "Help", "Offline help and guides", "Help & Guides", FeatureStatus.IMPLEMENTED, "Help catalogue and topic API", "help.view"),
)


def feature_registry() -> tuple[PlatformFeature, ...]:
    return FEATURES


def registry_payload() -> dict:
    return {"items": [feature.as_dict() for feature in FEATURES]}


def parity_payload() -> dict:
    platforms = tuple(Platform)
    summary: dict[str, dict[str, int | bool]] = {}
    for platform in platforms:
        statuses = [
            impl.status
            for feature in FEATURES
            for impl in feature.implementations
            if impl.platform == platform
        ]
        implemented = sum(status == FeatureStatus.IMPLEMENTED for status in statuses)
        partial = sum(status == FeatureStatus.PARTIAL for status in statuses)
        missing = sum(status == FeatureStatus.NOT_IMPLEMENTED for status in statuses)
        summary[platform.value] = {
            "total": len(statuses),
            "implemented": implemented,
            "partial": partial,
            "missing": missing,
            "functionally_complete": missing == 0 and partial == 0,
        }
    return {"platforms": summary, "feature_count": len(FEATURES)}


def validate_registry(features: Iterable[PlatformFeature] = FEATURES) -> None:
    seen: set[str] = set()
    required = set(Platform)
    for feature in features:
        if feature.feature_id in seen:
            raise ValueError(f"duplicate feature id: {feature.feature_id}")
        seen.add(feature.feature_id)
        platforms = {item.platform for item in feature.implementations}
        if platforms != required:
            raise ValueError(f"{feature.feature_id} does not declare all supported platforms")
        if not feature.permission.strip():
            raise ValueError(f"{feature.feature_id} has no permission contract")


validate_registry()
