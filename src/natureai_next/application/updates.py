"""Offline update discovery, verification, and staging."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from natureai_next import __version__
from natureai_next.application.update_trust import verify_signed_update_index


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
    size: int
    release_id: str
    release_digest: str
    signer_key_id: str
    release_notes: str
    channel: str = "stable"
    security_install_evidence: dict[str, object] | None = None


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
    """Discover and safely stage authenticated updates from offline media."""

    INDEX_NAME = "update-index.json"

    def __init__(
        self,
        *,
        trust_anchor_path: Path,
        current_version: str = __version__,
        product: str = "Fieldora",
    ) -> None:
        self._trust_anchor_path = trust_anchor_path.expanduser().resolve()
        self._current_version = current_version
        self._product = product

    def check(self, source: Path, *, channel: str = "stable") -> UpdateCandidate | None:
        source = source.expanduser().resolve()
        index_path = source / self.INDEX_NAME
        if not index_path.is_file() or index_path.is_symlink():
            raise FileNotFoundError(f"update index not found: {index_path}")
        # The administrator trust anchor is supplied at service composition time, never
        # discovered from the user-selected update source.
        verified = verify_signed_update_index(index_path, self._trust_anchor_path)
        payload = verified.payload
        if payload.get("product") != self._product:
            raise ValueError("update package is for a different product")
        candidate_channel = str(payload["channel"])
        if candidate_channel != channel:
            return None
        version = str(payload["version"])
        minimum = str(payload["minimum_supported_version"])
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
        if not package_path.is_file() or package_path.is_symlink():
            raise FileNotFoundError(f"update package not found: {package_path}")
        expected = str(payload["sha256"]).casefold()
        actual = self._sha256(package_path)
        if actual != expected:
            raise ValueError("update package checksum does not match the signed update index")
        expected_size = int(payload["size"])
        if expected_size < 0 or package_path.stat().st_size != expected_size:
            raise ValueError("update package size does not match the signed update index")
        security_install = payload["security_install"]
        if not isinstance(security_install, dict):
            raise ValueError("authenticated Security Install evidence is required for native updates")
        notes_value = payload.get("release_notes", "")
        notes_path = source / str(notes_value) if notes_value else None
        release_notes = notes_path.read_text(encoding="utf-8") if notes_path and notes_path.is_file() else str(notes_value)
        return UpdateCandidate(
            product=self._product,
            version=version,
            minimum_supported_version=minimum,
            package_path=package_path,
            sha256=expected,
            size=expected_size,
            release_id=str(payload["release_id"]),
            release_digest=str(payload["release_digest"]).casefold(),
            signer_key_id=verified.key_id,
            release_notes=release_notes,
            channel=candidate_channel,
            security_install_evidence=dict(security_install),
        )

    def stage(self, candidate: UpdateCandidate, staging_directory: Path) -> StagedUpdate:
        if not isinstance(candidate.security_install_evidence, dict):
            raise ValueError("authenticated Security Install evidence is required for native updates")
        staging_directory.mkdir(parents=True, exist_ok=True)
        target = staging_directory / candidate.package_path.name
        if target.exists():
            target.unlink()
        shutil.copy2(candidate.package_path, target)
        if self._sha256(target) != candidate.sha256 or target.stat().st_size != candidate.size:
            target.unlink(missing_ok=True)
            raise ValueError("staged update failed signed integrity verification")
        request = staging_directory / "pending-update.json"
        payload = {
            "format": "natureai-next.pending-update",
            "format_version": 2,
            "product": candidate.product,
            "from_version": self._current_version,
            "version": candidate.version,
            "package": target.name,
            "sha256": candidate.sha256,
            "size": candidate.size,
            "release_id": candidate.release_id,
            "release_digest": candidate.release_digest,
            "signer_key_id": candidate.signer_key_id,
            "security_install": candidate.security_install_evidence,
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
