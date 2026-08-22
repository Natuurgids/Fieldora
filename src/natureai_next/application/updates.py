"""Offline update discovery, verification, and staging."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from natureai_next import __version__


@dataclass(frozen=True, slots=True)
class UpdateSettings:
    source: Path | None = None
    check_at_startup: bool = False
    channel: str = "stable"


@dataclass(frozen=True, slots=True)
class UpdateCandidate:
    product: str
    version: str
    minimum_supported_version: str
    package_path: Path
    sha256: str
    release_notes: str
    channel: str = "stable"


@dataclass(frozen=True, slots=True)
class StagedUpdate:
    candidate: UpdateCandidate
    staged_package: Path
    request_path: Path


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError as exc:
        raise ValueError(f"invalid semantic version: {value}") from exc


class UpdateSettingsStore:
    """Persist update preferences without changing the application config schema."""

    def load(self, path: Path) -> UpdateSettings:
        if not path.exists():
            return UpdateSettings()
        data = json.loads(path.read_text(encoding="utf-8"))
        source = data.get("source")
        return UpdateSettings(
            source=Path(source) if isinstance(source, str) and source else None,
            check_at_startup=bool(data.get("check_at_startup", False)),
            channel=str(data.get("channel", "stable")),
        )

    def save(self, path: Path, settings: UpdateSettings) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "natureai-next.update-settings",
            "format_version": 1,
            "source": str(settings.source) if settings.source else "",
            "check_at_startup": settings.check_at_startup,
            "channel": settings.channel,
        }
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(path)


class OfflineUpdateService:
    """Discover and safely stage updates from a trusted filesystem location."""

    INDEX_NAME = "update-index.json"

    def __init__(self, *, current_version: str = __version__, product: str = "Fieldora") -> None:
        self._current_version = current_version
        self._product = product

    def check(self, source: Path, *, channel: str = "stable") -> UpdateCandidate | None:
        source = source.expanduser()
        index_path = source / self.INDEX_NAME
        if not index_path.is_file():
            raise FileNotFoundError(f"update index not found: {index_path}")
        payload: dict[str, Any] = json.loads(index_path.read_text(encoding="utf-8"))
        if (
            payload.get("format") != "natureai-next.update-index"
            or payload.get("format_version") != 1
        ):
            raise ValueError("unsupported update index format")
        if payload.get("product") != self._product:
            raise ValueError("update package is for a different product")
        candidate_channel = str(payload.get("channel", "stable"))
        if candidate_channel != channel:
            return None
        version = str(payload["version"])
        minimum = str(payload.get("minimum_supported_version", "0.0.0"))
        if _version_tuple(version) <= _version_tuple(self._current_version):
            return None
        if _version_tuple(self._current_version) < _version_tuple(minimum):
            raise ValueError(
                f"Fieldora {self._current_version} is older than the minimum supported update version {minimum}"
            )
        package_name = str(payload["package"])
        if Path(package_name).name != package_name:
            raise ValueError("update package must be in the configured update folder")
        package_path = source / package_name
        if not package_path.is_file():
            raise FileNotFoundError(f"update package not found: {package_path}")
        expected = str(payload["sha256"]).casefold()
        actual = self._sha256(package_path)
        if actual != expected:
            raise ValueError("update package checksum does not match the update index")
        notes_value = payload.get("release_notes", "")
        notes_path = source / str(notes_value) if notes_value else None
        release_notes = (
            notes_path.read_text(encoding="utf-8")
            if notes_path and notes_path.is_file()
            else str(notes_value)
        )
        return UpdateCandidate(
            product=self._product,
            version=version,
            minimum_supported_version=minimum,
            package_path=package_path,
            sha256=expected,
            release_notes=release_notes,
            channel=candidate_channel,
        )

    def stage(self, candidate: UpdateCandidate, staging_directory: Path) -> StagedUpdate:
        staging_directory.mkdir(parents=True, exist_ok=True)
        target = staging_directory / candidate.package_path.name
        if target.exists():
            target.unlink()
        shutil.copy2(candidate.package_path, target)
        if self._sha256(target) != candidate.sha256:
            target.unlink(missing_ok=True)
            raise ValueError("staged update failed checksum verification")
        request = staging_directory / "pending-update.json"
        payload = {
            "format": "natureai-next.pending-update",
            "format_version": 1,
            "product": candidate.product,
            "version": candidate.version,
            "package": target.name,
            "sha256": candidate.sha256,
            "status": "staged",
        }
        request.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return StagedUpdate(candidate=candidate, staged_package=target, request_path=request)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
