"""Validated plugin capability registries."""

from __future__ import annotations

from dataclasses import dataclass, field

from natureai_next.plugin_api import MetadataReader, PluginCapability, PluginManifest
from natureai_next.shared.errors import ErrorCode, ErrorDescriptor, PluginError


@dataclass(slots=True)
class PluginRegistry:
    manifest: PluginManifest
    _metadata_readers: dict[str, MetadataReader] = field(default_factory=dict)

    def register_metadata_reader(self, reader: MetadataReader) -> None:
        self._require(PluginCapability.FILESYSTEM_ASSET_READ)
        if not reader.reader_id.startswith(f"{self.manifest.plugin_id}."):
            raise PluginError(
                ErrorDescriptor(
                    ErrorCode.PLUGIN_MANIFEST_INVALID,
                    "Plugin reader ID must be prefixed by the plugin ID.",
                    entity_ids=(self.manifest.plugin_id, reader.reader_id),
                )
            )
        if reader.reader_id in self._metadata_readers:
            raise PluginError(
                ErrorDescriptor(
                    ErrorCode.PLUGIN_MANIFEST_INVALID,
                    "Plugin registered a duplicate metadata reader ID.",
                    entity_ids=(self.manifest.plugin_id, reader.reader_id),
                )
            )
        self._metadata_readers[reader.reader_id] = reader

    @property
    def metadata_readers(self) -> tuple[MetadataReader, ...]:
        return tuple(self._metadata_readers.values())

    def _require(self, capability: PluginCapability) -> None:
        if capability not in self.manifest.capabilities:
            raise PluginError(
                ErrorDescriptor(
                    ErrorCode.PLUGIN_CAPABILITY_DENIED,
                    f"Plugin did not declare required capability {capability.value}.",
                    entity_ids=(self.manifest.plugin_id,),
                )
            )
