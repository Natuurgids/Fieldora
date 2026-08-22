"""Configuration precedence, validation, migrations, and persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, fields, replace
from pathlib import Path

from natureai_next.application.configuration import (
    CURRENT_CONFIG_SCHEMA_VERSION,
    EffectiveSettings,
    Settings,
    merge_dataclass,
)
from natureai_next.ports.configuration import ConfigurationStore
from natureai_next.shared.errors import ConfigurationError, ErrorCode, ErrorDescriptor

_SECTION_NAMES = {"application", "performance", "ai", "imports", "plugins"}


class ConfigurationService:
    """Build effective settings from ordered, named configuration sources."""

    def __init__(self, store: ConfigurationStore) -> None:
        self._store = store

    def read_source(self, path: Path) -> dict[str, object]:
        return self._migrate_if_needed(path, self._store.read(path))

    def load_files(self, sources: tuple[tuple[str, Path], ...]) -> EffectiveSettings:
        documents = tuple(
            (name, self._migrate_if_needed(path, self._store.read(path))) for name, path in sources
        )
        return self.load_documents(documents)

    def load_documents(
        self, sources: tuple[tuple[str, Mapping[str, object]], ...]
    ) -> EffectiveSettings:
        settings = Settings.defaults()
        origins: dict[str, str] = {}
        unknown: dict[str, object] = {}
        try:
            for source_name, document in sources:
                settings, source_unknown = self._apply_document(
                    settings, document, source_name, origins
                )
                unknown = _deep_merge(unknown, source_unknown)
            settings.validate()
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                ErrorDescriptor(
                    code=ErrorCode.CONFIG_INVALID,
                    summary="Configuration contains an invalid value.",
                    technical_detail=str(exc),
                    remediation="Correct the named setting or remove it to restore the default.",
                )
            ) from exc
        return EffectiveSettings(settings=settings, sources=origins, unknown=unknown)

    def save(self, path: Path, effective: EffectiveSettings) -> None:
        effective.settings.validate()
        document = _deep_merge(dict(effective.unknown), asdict(effective.settings))
        document["schema_version"] = effective.settings.schema_version
        self._store.write(path, document)

    def _apply_document(
        self,
        settings: Settings,
        document: Mapping[str, object],
        source_name: str,
        origins: dict[str, str],
    ) -> tuple[Settings, dict[str, object]]:
        updated = settings
        unknown: dict[str, object] = {}
        if "schema_version" in document:
            schema_version = document["schema_version"]
            if type(schema_version) is not int:
                raise TypeError("schema_version must be an integer")
            updated = replace(updated, schema_version=schema_version)
            origins["schema_version"] = source_name
        for key, raw_section in document.items():
            if key == "schema_version":
                continue
            if key not in _SECTION_NAMES:
                unknown[key] = raw_section
                continue
            if not isinstance(raw_section, Mapping):
                raise TypeError(f"{key} must be a table")
            section = getattr(updated, key)
            known_fields = {field.name for field in fields(section)}
            known_values = {
                name: value for name, value in raw_section.items() if name in known_fields
            }
            unknown_values = {
                name: value for name, value in raw_section.items() if name not in known_fields
            }
            updated = replace(updated, **{key: merge_dataclass(section, known_values)})
            for field_name in known_values:
                origins[f"{key}.{field_name}"] = source_name
            if unknown_values:
                unknown[key] = unknown_values
        return updated, unknown

    def _migrate_if_needed(self, path: Path, document: dict[str, object]) -> dict[str, object]:
        if not document:
            return document
        version = document.get("schema_version", 0)
        if type(version) is not int:
            raise ConfigurationError(
                ErrorDescriptor(
                    ErrorCode.CONFIG_INVALID, "Configuration schema_version must be an integer."
                )
            )
        if version > CURRENT_CONFIG_SCHEMA_VERSION:
            raise ConfigurationError(
                ErrorDescriptor(
                    ErrorCode.CONFIG_INVALID,
                    f"Configuration requires newer schema version {version}.",
                )
            )
        if version == CURRENT_CONFIG_SCHEMA_VERSION:
            return document
        self._store.backup(path, f"v{version}")
        migrated = dict(document)
        # Version 0 was the pre-versioned baseline; no keys require transformation.
        migrated["schema_version"] = CURRENT_CONFIG_SCHEMA_VERSION
        return migrated


def _deep_merge(base: dict[str, object], overlay: Mapping[str, object]) -> dict[str, object]:
    result = dict(base)
    for key, value in overlay.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, Mapping):
            result[key] = _deep_merge(existing, value)
        else:
            result[key] = value
    return result
