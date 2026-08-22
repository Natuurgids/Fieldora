"""Public test helpers for third-party plugin contract validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from natureai_next.plugin_api.models import PluginManifest, PluginPaths
from natureai_next.plugin_api.protocols import MetadataReader
from natureai_next.plugin_api.version import PLUGIN_API_VERSION


@dataclass(slots=True)
class CapturingRegistry:
    metadata_readers: list[MetadataReader] = field(default_factory=list)

    def register_metadata_reader(self, reader: MetadataReader) -> None:
        self.metadata_readers.append(reader)


@dataclass(slots=True)
class CapturingLogger:
    records: list[tuple[str, str, dict[str, object] | None]] = field(default_factory=list)

    def info(self, message: str, *, context: dict[str, object] | None = None) -> None:
        self.records.append(("info", message, context))

    def warning(self, message: str, *, context: dict[str, object] | None = None) -> None:
        self.records.append(("warning", message, context))

    def error(self, message: str, *, context: dict[str, object] | None = None) -> None:
        self.records.append(("error", message, context))


@dataclass(slots=True)
class FakePluginContext:
    manifest: PluginManifest
    root: Path
    application_version: str = "0.1.0"
    plugin_api_version: str = PLUGIN_API_VERSION
    logger: CapturingLogger = field(default_factory=CapturingLogger)
    registry: CapturingRegistry = field(default_factory=CapturingRegistry)

    @property
    def paths(self) -> PluginPaths:
        return PluginPaths(
            package_resources=self.root / "resources",
            global_data=self.root / "global",
            library_data=self.root / "library",
        )
