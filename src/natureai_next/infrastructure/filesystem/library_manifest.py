"""Atomic library manifest persistence and compatibility normalization."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from natureai_next.domain.library import LibraryManifest
from natureai_next.infrastructure.filesystem.atomic import atomic_write_bytes

_CURRENT_FIELDS = {
    "format_version",
    "library_public_id",
    "display_name",
    "created_at_us",
    "database_filename",
}
_LEGACY_IGNORED_FIELDS = {"sha256", "size_bytes"}


def write_manifest(path: Path, manifest: LibraryManifest) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _format_version(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("manifest format must be a version number")
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    digits = "".join(ch for ch in text.rsplit("-", 1)[-1] if ch.isdigit())
    if digits:
        return int(digits)
    raise ValueError(f"unsupported manifest format value: {value!r}")


def _timestamp_us(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("created_at_utc must be a timestamp")
    if isinstance(value, int | float):
        numeric = int(value)
        if numeric < 100_000_000_000:  # seconds
            return numeric * 1_000_000
        if numeric < 100_000_000_000_000:  # milliseconds
            return numeric * 1_000
        return numeric
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp() * 1_000_000)


def _normalize_manifest(value: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    normalized = dict(value)
    changed = False

    aliases = {
        "format": "format_version",
        "library_name": "display_name",
        "database_file": "database_filename",
    }
    for legacy, current in aliases.items():
        if legacy in normalized:
            if current not in normalized:
                normalized[current] = normalized[legacy]
            del normalized[legacy]
            changed = True

    if "created_at_utc" in normalized:
        if "created_at_us" not in normalized:
            normalized["created_at_us"] = _timestamp_us(normalized["created_at_utc"])
        del normalized["created_at_utc"]
        changed = True

    if "format_version" in normalized:
        converted = _format_version(normalized["format_version"])
        changed = changed or converted != normalized["format_version"]
        normalized["format_version"] = converted

    for obsolete in _LEGACY_IGNORED_FIELDS:
        if obsolete in normalized:
            del normalized[obsolete]
            changed = True

    missing = sorted(_CURRENT_FIELDS - normalized.keys())
    if missing:
        raise ValueError("library manifest is missing required fields: " + ", ".join(missing))

    unsupported = sorted(normalized.keys() - _CURRENT_FIELDS)
    if unsupported:
        raise ValueError("library manifest contains unsupported fields: " + ", ".join(unsupported))

    return normalized, changed


def _backup_original(path: Path) -> Path:
    backup = path.with_name(path.name + ".before-normalization")
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def read_manifest(path: Path) -> LibraryManifest:
    """Read the current manifest without modifying any library file."""
    try:
        source_bytes = path.read_bytes()
        raw = source_bytes.decode("utf-8-sig")
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"library manifest is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("library manifest must contain a JSON object")
    if set(value) != _CURRENT_FIELDS:
        missing = sorted(_CURRENT_FIELDS - value.keys())
        unsupported = sorted(value.keys() - _CURRENT_FIELDS)
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unsupported:
            details.append("unsupported: " + ", ".join(unsupported))
        raise ValueError("library manifest is not canonical (" + "; ".join(details) + ")")
    manifest = LibraryManifest(**value)
    if manifest.format_version != 1:
        raise ValueError(f"unsupported library manifest format_version: {manifest.format_version}")
    if manifest.database_filename != "library.sqlite3":
        raise ValueError("unsupported database_filename; expected library.sqlite3")
    return manifest


def normalize_manifest(path: Path) -> LibraryManifest:
    """Explicitly normalize a recognized legacy manifest after operator approval."""
    source_bytes = path.read_bytes()
    value = json.loads(source_bytes.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("library manifest must contain a JSON object")
    normalized, changed = _normalize_manifest(value)
    manifest = LibraryManifest(**normalized)
    if manifest.format_version != 1 or manifest.database_filename != "library.sqlite3":
        raise ValueError("legacy manifest cannot be normalized for this release")
    if changed or source_bytes.startswith(b"\xef\xbb\xbf"):
        _backup_original(path)
        write_manifest(path, manifest)
    return manifest
