"""Verified backup inspection and safe restore staging."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VerifiedBackup:
    database_path: Path
    manifest_path: Path
    library_name: str
    created_at_utc: str
    size_bytes: int
    sha256: str
    subsystem_databases: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class StagedRestore:
    staged_database: Path
    staged_manifest: Path
    request_path: Path
    emergency_backup: Path


class LibraryRecoveryService:
    """Verify NatureAI_Next backup manifests and stage restart-safe restores."""

    def verify(self, database_path: Path) -> VerifiedBackup:
        database_path = database_path.expanduser().resolve()
        if not database_path.is_file():
            raise FileNotFoundError(database_path)
        manifest_path = database_path.with_suffix(database_path.suffix + ".manifest.json")
        if not manifest_path.is_file():
            raise FileNotFoundError(f"backup manifest not found: {manifest_path}")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        supported = {
            ("natureai-next.database-backup", 1),
            ("natureai-next.storage-aware-backup", 2),
        }
        if (payload.get("format"), payload.get("format_version")) not in supported:
            raise ValueError("unsupported backup manifest format")
        if payload.get("database_file") != database_path.name:
            raise ValueError("backup manifest names a different database file")
        size = database_path.stat().st_size
        if payload.get("size_bytes") != size:
            raise ValueError("backup size does not match its manifest")
        digest = hashlib.sha256()
        with database_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if payload.get("sha256") != actual:
            raise ValueError("backup checksum does not match its manifest")
        subsystem_entries: list[dict[str, object]] = []
        storage_root = database_path.with_suffix(database_path.suffix + ".files")
        for raw in payload.get("subsystem_databases", []):
            entry = dict(raw)
            relative = Path(str(entry.get("file", "")))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("backup contains an unsafe subsystem database path")
            subsystem = storage_root / relative
            if not subsystem.is_file():
                raise FileNotFoundError(f"subsystem backup not found: {subsystem}")
            if subsystem.stat().st_size != int(entry.get("size_bytes", -1)):
                raise ValueError("subsystem backup size does not match its manifest")
            subsystem_hash = hashlib.sha256()
            with subsystem.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    subsystem_hash.update(chunk)
            subsystem_digest = subsystem_hash.hexdigest()
            if subsystem_digest != str(entry.get("sha256", "")):
                raise ValueError("subsystem backup checksum does not match its manifest")
            subsystem_entries.append(entry)
        return VerifiedBackup(
            database_path=database_path,
            manifest_path=manifest_path,
            library_name=str(payload.get("library_name", "Aperture Library")),
            created_at_utc=str(payload.get("created_at_utc", "")),
            size_bytes=size,
            sha256=actual,
            subsystem_databases=tuple(subsystem_entries),
        )

    def list_backups(self, directory: Path) -> tuple[VerifiedBackup, ...]:
        directory = directory.expanduser().resolve()
        if not directory.exists():
            return ()
        results: list[VerifiedBackup] = []
        for candidate in sorted(
            directory.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            try:
                results.append(self.verify(candidate))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return tuple(results)

    def stage_restore(
        self,
        backup: VerifiedBackup,
        *,
        staging_directory: Path,
        current_database: Path,
        emergency_backup: Path,
        subsystem_targets: dict[str, Path] | None = None,
    ) -> StagedRestore:
        staging_directory = staging_directory.expanduser().resolve()
        current_database = current_database.expanduser().resolve()
        emergency_backup = emergency_backup.expanduser().resolve()
        self.verify(backup.database_path)
        if not current_database.is_file():
            raise FileNotFoundError(f"current library database not found: {current_database}")
        if not emergency_backup.is_file():
            raise FileNotFoundError(f"emergency backup not found: {emergency_backup}")
        staging_directory.mkdir(parents=True, exist_ok=True)
        staged_database = staging_directory / "restore.sqlite3"
        staged_manifest = staging_directory / "restore.sqlite3.manifest.json"
        temp_database = staged_database.with_suffix(".sqlite3.tmp")
        temp_manifest = staged_manifest.with_suffix(staged_manifest.suffix + ".tmp")
        shutil.copy2(backup.database_path, temp_database)
        staged_payload = json.loads(backup.manifest_path.read_text(encoding="utf-8"))
        staged_payload["database_file"] = staged_database.name
        temp_manifest.write_text(
            json.dumps(staged_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temp_database.replace(staged_database)
        temp_manifest.replace(staged_manifest)
        source_root = backup.database_path.with_suffix(
            backup.database_path.suffix + ".files"
        )
        staged_storage_root = staged_database.with_suffix(
            staged_database.suffix + ".files"
        )
        for entry in backup.subsystem_databases:
            source = source_root / str(entry["file"])
            staged_copy = staged_storage_root / str(entry["file"])
            staged_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged_copy)
        staged_verified = self.verify(staged_database)
        request_path = staging_directory / "pending-restore.json"
        request = {
            "format": "natureai-next.pending-restore",
            "format_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "target_database": str(current_database),
            "staged_database": str(staged_verified.database_path),
            "sha256": staged_verified.sha256,
            "emergency_backup": str(emergency_backup),
            "subsystem_databases": [],
        }
        targets = subsystem_targets or {}
        for entry in backup.subsystem_databases:
            key = str(entry["key"])
            target = targets.get(key)
            if target is None:
                continue
            source = staged_storage_root / str(entry["file"])
            staged_subsystem = staging_directory / "subsystems" / f"{key}.sqlite3"
            staged_subsystem.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged_subsystem)
            request["subsystem_databases"].append(
                {
                    "key": key, "staged_database": str(staged_subsystem),
                    "target_database": str(target.expanduser().resolve()),
                    "sha256": str(entry["sha256"]),
                }
            )
        temp_request = request_path.with_suffix(".json.tmp")
        temp_request.write_text(
            json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temp_request.replace(request_path)
        return StagedRestore(staged_database, staged_manifest, request_path, emergency_backup)
