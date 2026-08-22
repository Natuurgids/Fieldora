"""Storage-aware verified Aperture backup orchestration."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class BackupScope(StrEnum):
    CATALOG_ONLY = "catalog_only"
    CATALOG_AND_MANAGED_ORIGINALS = "catalog_and_managed_originals"
    CATALOG_AND_REFERENCE_MANIFEST = "catalog_and_reference_manifest"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class BackupResult:
    database_path: Path
    manifest_path: Path
    size_bytes: int
    sha256: str
    created_at_utc: str
    scope: BackupScope = BackupScope.CATALOG_ONLY
    managed_files_copied: int = 0
    referenced_files_listed: int = 0
    subsystem_databases_copied: int = 0


class LibraryBackupService:
    """Create a verified catalog backup and optional storage-aware payload."""

    def __init__(self, backup_database: Callable[[Path], Path], *, library_name: str,
                 library_database_path: Path | None = None,
                 additional_databases: dict[str, Path] | None = None) -> None:
        self._backup_database = backup_database
        self._library_name = library_name
        self._library_database_path = Path(library_database_path) if library_database_path else None
        self._additional_databases = {
            str(key): Path(value) for key, value in (additional_databases or {}).items()
        }

    def create(self, destination: Path, *, scope: BackupScope = BackupScope.CATALOG_ONLY) -> BackupResult:
        destination = destination.expanduser().resolve()
        if destination.exists():
            raise FileExistsError(f"backup already exists: {destination}")
        if destination.suffix.casefold() not in {".sqlite3", ".db"}:
            destination = destination.with_suffix(".sqlite3")
        destination.parent.mkdir(parents=True, exist_ok=True)
        created = self._backup_database(destination)
        digest = self._digest(created)
        created_at = datetime.now(UTC).isoformat()
        storage_root = created.with_suffix(created.suffix + ".files")
        managed_files = 0
        references: list[dict[str, object]] = []
        subsystem_entries: list[dict[str, object]] = []
        for key, source in sorted(self._additional_databases.items()):
            if not source.is_file():
                continue
            target = storage_root / "databases" / f"{key}.sqlite3"
            target.parent.mkdir(parents=True, exist_ok=True)
            source_connection = sqlite3.connect(
                f"file:{source.resolve().as_posix()}?mode=ro", uri=True
            )
            destination_connection = sqlite3.connect(target)
            try:
                source_connection.backup(destination_connection)
                result = destination_connection.execute("PRAGMA integrity_check").fetchone()
                if result is None or str(result[0]).casefold() != "ok":
                    raise OSError(f"backup integrity check failed for {source}")
            finally:
                destination_connection.close()
                source_connection.close()
            subsystem_entries.append(
                {
                    "key": key, "file": target.relative_to(storage_root).as_posix(),
                    "size_bytes": target.stat().st_size, "sha256": self._digest(target),
                }
            )
        if scope is not BackupScope.CATALOG_ONLY:
            locations = self._storage_locations(created)
            for row in locations:
                entry = {
                    "asset_public_id": row["asset_public_id"], "role": row["role"],
                    "path": row["normalized_path"], "sha256": row["sha256"],
                    "size_bytes": row["file_size"], "health": row["health"],
                    "provider": row["provider_name"],
                }
                if row["role"] == "source":
                    references.append(entry)
                if scope in {BackupScope.CATALOG_AND_MANAGED_ORIGINALS, BackupScope.COMPLETE} and row["role"] == "aperture_master":
                    source = Path(row["normalized_path"])
                    if source.is_file():
                        relative = Path(str(row["sha256"] or source.name)[:2]) / source.name
                        target = storage_root / "managed-originals" / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                        if row["sha256"] and self._digest(target) != row["sha256"]:
                            raise OSError(f"backup verification failed for {source}")
                        managed_files += 1
            if scope in {BackupScope.CATALOG_AND_REFERENCE_MANIFEST, BackupScope.COMPLETE}:
                storage_root.mkdir(parents=True, exist_ok=True)
                (storage_root / "referenced-originals.json").write_text(
                    json.dumps({"format":"aperture.referenced-original-manifest","version":1,"files":references}, indent=2, sort_keys=True)+"\n",
                    encoding="utf-8",
                )
        manifest = created.with_suffix(created.suffix + ".manifest.json")
        payload = {
            "format": "natureai-next.storage-aware-backup", "format_version": 2,
            "library_name": self._library_name, "created_at_utc": created_at,
            "database_file": created.name, "size_bytes": created.stat().st_size,
            "sha256": digest, "scope": scope.value,
            "managed_files_copied": managed_files, "referenced_files_listed": len(references),
            "storage_payload_directory": storage_root.name if storage_root.exists() else None,
            "subsystem_databases": subsystem_entries,
        }
        temp = manifest.with_suffix(manifest.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(manifest)
        return BackupResult(
            created, manifest, payload["size_bytes"], digest, created_at, scope,
            managed_files, len(references), len(subsystem_entries),
        )

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _storage_locations(database_path: Path) -> list[sqlite3.Row]:
        connection = sqlite3.connect(database_path); connection.row_factory = sqlite3.Row
        try:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='asset_storage_locations'").fetchone()
            if not exists: return []
            return list(connection.execute(
                "SELECT l.*,a.public_id asset_public_id,p.display_name provider_name FROM asset_storage_locations l JOIN assets a ON a.id=l.asset_id JOIN storage_providers p ON p.id=l.provider_id ORDER BY a.id,l.role,l.id"
            ))
        finally:
            connection.close()


def suggested_backup_name(library_name: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "-" for character in library_name)
    safe = safe.strip("-") or "Aperture-Library"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{safe}-{stamp}.sqlite3"
