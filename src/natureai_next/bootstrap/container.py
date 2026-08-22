"""Application composition root for foundation services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.capabilities import (
    CapabilityRegistry,
    build_foundation_capability_registry,
)
from natureai_next.application.configuration import EffectiveSettings
from natureai_next.application.configuration_service import ConfigurationService
from natureai_next.bootstrap.paths import ApplicationPaths, resolve_application_paths
from natureai_next.bootstrap.subsystems import build_subsystem_registry
from natureai_next.infrastructure.diagnostics.logging import configure_logging
from natureai_next.infrastructure.diagnostics.system_services import (
    SystemClock,
    SystemUuidGenerator,
)
from natureai_next.infrastructure.filesystem.configuration_store import TomlConfigurationStore
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry


@dataclass(frozen=True, slots=True)
class FoundationContainer:
    paths: ApplicationPaths
    settings: EffectiveSettings
    clock: SystemClock
    uuid_generator: SystemUuidGenerator
    configuration_service: ConfigurationService
    subsystem_registry: SubsystemDatabaseRegistry
    capability_registry: CapabilityRegistry


def build_foundation_container(
    *,
    config_root: Path | None = None,
    session_overrides: dict[str, object] | None = None,
) -> FoundationContainer:
    paths = resolve_application_paths(config_root)
    paths.ensure_directories()
    configuration_service = ConfigurationService(TomlConfigurationStore())
    sources: list[tuple[str, dict[str, object]]] = []
    for name, path in (
        ("application", paths.config_file),
        ("user", paths.preferences_file),
    ):
        document = configuration_service.read_source(path)
        if document:
            sources.append((name, document))
    if session_overrides:
        sources.append(("session", session_overrides))
    effective = configuration_service.load_documents(tuple(sources))
    configure_logging(
        paths.logs_dir,
        effective.settings.application.log_level.value,
        effective.settings.application.log_retention_days,
    )
    subsystem_registry = build_subsystem_registry(paths)
    return FoundationContainer(
        paths=paths,
        settings=effective,
        clock=SystemClock(),
        uuid_generator=SystemUuidGenerator(),
        configuration_service=configuration_service,
        subsystem_registry=subsystem_registry,
        capability_registry=build_foundation_capability_registry(subsystem_registry),
    )
