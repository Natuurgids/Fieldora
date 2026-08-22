"""Plugin manifest parsing and compatibility validation without importing plugins."""

from __future__ import annotations

import re
from collections.abc import Mapping

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from natureai_next.plugin_api import PluginCapability, PluginKind, PluginManifest
from natureai_next.shared.errors import ErrorCode, ErrorDescriptor, PluginError

_PLUGIN_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+){2,}$")
_REQUIRED_STRING_FIELDS = (
    "plugin_id",
    "display_name",
    "version",
    "provider",
    "description",
    "license",
    "plugin_api_specifier",
    "minimum_application_version",
    "entry_point",
)


def parse_manifest(document: Mapping[str, object]) -> PluginManifest:
    missing = [name for name in _REQUIRED_STRING_FIELDS if not document.get(name)]
    if missing:
        _invalid(f"Missing required manifest fields: {', '.join(missing)}")
    for name in _REQUIRED_STRING_FIELDS:
        if not isinstance(document[name], str):
            _invalid(f"Manifest field {name} must be a string")
    plugin_id = str(document["plugin_id"])
    if not _PLUGIN_ID.fullmatch(plugin_id):
        _invalid("plugin_id must be a reverse-domain lowercase identifier")
    try:
        Version(str(document["version"]))
        Version(str(document["minimum_application_version"]))
        SpecifierSet(str(document["plugin_api_specifier"]))
    except (InvalidVersion, InvalidSpecifier) as exc:
        _invalid(str(exc), cause=exc)
    raw_capabilities = document.get("capabilities", [])
    if not isinstance(raw_capabilities, list):
        _invalid("capabilities must be an array")
    try:
        capabilities = frozenset(PluginCapability(item) for item in raw_capabilities)
    except (ValueError, TypeError) as exc:
        _invalid(f"Unknown plugin capability: {exc}", cause=exc)
    return PluginManifest(
        plugin_id=plugin_id,
        display_name=str(document["display_name"]),
        version=str(document["version"]),
        provider=str(document["provider"]),
        description=str(document["description"]),
        license=str(document["license"]),
        plugin_api_specifier=str(document["plugin_api_specifier"]),
        minimum_application_version=str(document["minimum_application_version"]),
        capabilities=capabilities,
        entry_point=str(document["entry_point"]),
        homepage=_optional_string(document, "homepage"),
        support=_optional_string(document, "support"),
        publisher_identity=_optional_string(document, "publisher_identity"),
        kind=_plugin_kind(document),
        input_kinds=_string_tuple(document, "input_kinds"),
        output_shapes=_string_tuple(document, "output_shapes"),
        parameters=_mapping_tuple(document, "parameters"),
        offline=_optional_bool(document, "offline", default=True),
        bundle_files=_string_tuple(document, "bundle_files"),
        checksums=_string_mapping(document, "checksums"),
        attribution=_optional_string(document, "attribution"),
    )


def validate_compatibility(
    manifest: PluginManifest, *, api_version: str, application_version: str
) -> None:
    api = Version(api_version)
    application = Version(application_version)
    if api not in SpecifierSet(manifest.plugin_api_specifier) or application < Version(
        manifest.minimum_application_version
    ):
        raise PluginError(
            ErrorDescriptor(
                code=ErrorCode.PLUGIN_INCOMPATIBLE,
                summary=f"Plugin {manifest.display_name} is incompatible with this application version.",
                entity_ids=(manifest.plugin_id,),
                remediation="Install a compatible plugin release or update NatureAI Next.",
            )
        )


def _optional_string(document: Mapping[str, object], key: str) -> str | None:
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        _invalid(f"Manifest field {key} must be a string")
    return value


def _invalid(detail: str, *, cause: Exception | None = None) -> None:
    error = PluginError(
        ErrorDescriptor(
            code=ErrorCode.PLUGIN_MANIFEST_INVALID,
            summary="Plugin manifest is invalid.",
            technical_detail=detail,
        )
    )
    if cause is None:
        raise error
    raise error from cause


def _plugin_kind(document: Mapping[str, object]) -> PluginKind:
    raw = document.get("kind", PluginKind.GENERAL.value)
    try:
        return PluginKind(str(raw))
    except ValueError as exc:
        _invalid(f"Unknown plugin kind: {raw}", cause=exc)


def _string_tuple(document: Mapping[str, object], key: str) -> tuple[str, ...]:
    raw = document.get(key, [])
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        _invalid(f"Manifest field {key} must be an array of strings")
    return tuple(raw)


def _mapping_tuple(document: Mapping[str, object], key: str) -> tuple[Mapping[str, object], ...]:
    raw = document.get(key, [])
    if not isinstance(raw, list) or any(not isinstance(item, Mapping) for item in raw):
        _invalid(f"Manifest field {key} must be an array of objects")
    return tuple(dict(item) for item in raw)


def _string_mapping(document: Mapping[str, object], key: str) -> Mapping[str, str]:
    raw = document.get(key, {})
    if not isinstance(raw, Mapping) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in raw.items()
    ):
        _invalid(f"Manifest field {key} must be a string mapping")
    return {str(k): str(v) for k, v in raw.items()}


def _optional_bool(document: Mapping[str, object], key: str, *, default: bool) -> bool:
    value = document.get(key, default)
    if not isinstance(value, bool):
        _invalid(f"Manifest field {key} must be a boolean")
    return value
