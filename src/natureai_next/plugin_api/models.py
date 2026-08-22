"""Immutable public plugin data contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class PluginKind(StrEnum):
    GENERAL = "general"
    CAPABILITY = "capability"
    SOURCE = "source"


class AvailabilityState(StrEnum):
    INSTALLED_LOCALLY = "installed_locally"
    AVAILABLE_OFFLINE = "available_offline"
    REQUIRES_DOWNLOAD = "requires_download"
    INACTIVE = "inactive"
    SOURCE_REMOVED = "source_removed"
    UPDATE_AVAILABLE = "update_available"


class PluginCapability(StrEnum):
    FILESYSTEM_PLUGIN_DATA = "filesystem.plugin_data"
    FILESYSTEM_EXPORT = "filesystem.export"
    FILESYSTEM_ASSET_READ = "filesystem.asset_read"
    UI_CONTRIBUTION = "ui.contribution"
    MODEL_LOADING = "ai.model_loading"
    TAXONOMY_INSTALLATION = "taxonomy.installation"
    DATABASE_STORAGE = "database.plugin_storage"
    RESTRICTED_UPDATE_TRANSPORT = "network.restricted_update_transport"


@dataclass(frozen=True, slots=True)
class PluginManifest:
    plugin_id: str
    display_name: str
    version: str
    provider: str
    description: str
    license: str
    plugin_api_specifier: str
    minimum_application_version: str
    capabilities: frozenset[PluginCapability]
    entry_point: str
    homepage: str | None = None
    support: str | None = None
    publisher_identity: str | None = None
    kind: PluginKind = PluginKind.GENERAL
    input_kinds: tuple[str, ...] = ()
    output_shapes: tuple[str, ...] = ()
    parameters: tuple[Mapping[str, object], ...] = ()
    offline: bool = True
    bundle_files: tuple[str, ...] = ()
    checksums: Mapping[str, str] = field(default_factory=dict)
    attribution: str | None = None


@dataclass(frozen=True, slots=True)
class MetadataField:
    name: str
    value: str | int | float | bool
    source: str


@dataclass(frozen=True, slots=True)
class MetadataReadResult:
    fields: tuple[MetadataField, ...]
    warnings: tuple[str, ...]
    raw_fields: Mapping[str, str] = field(default_factory=dict)
    reader_version: str = "1"


@dataclass(frozen=True, slots=True)
class PluginPaths:
    package_resources: Path
    global_data: Path
    library_data: Path | None
