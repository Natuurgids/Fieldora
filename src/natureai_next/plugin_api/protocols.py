"""Stable public plugin protocols."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from natureai_next.plugin_api.models import MetadataReadResult, PluginManifest, PluginPaths


@runtime_checkable
class StructuredPluginLogger(Protocol):
    def info(self, message: str, *, context: dict[str, object] | None = None) -> None: ...
    def warning(self, message: str, *, context: dict[str, object] | None = None) -> None: ...
    def error(self, message: str, *, context: dict[str, object] | None = None) -> None: ...


@runtime_checkable
class MetadataReader(Protocol):
    reader_id: str
    supported_mime_types: frozenset[str]

    def read(self, source: Path) -> MetadataReadResult: ...


@runtime_checkable
class RegistrationRegistry(Protocol):
    def register_metadata_reader(self, reader: MetadataReader) -> None: ...


@runtime_checkable
class PluginContext(Protocol):
    application_version: str
    plugin_api_version: str
    manifest: PluginManifest
    paths: PluginPaths
    logger: StructuredPluginLogger
    registry: RegistrationRegistry


@runtime_checkable
class Plugin(Protocol):
    def register(self, context: PluginContext) -> None: ...
    def deactivate(self) -> None: ...
