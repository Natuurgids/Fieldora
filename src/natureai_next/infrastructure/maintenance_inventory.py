"""Filesystem and SQLite adapter for the Maintenance inventory contract."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from natureai_next.application.library import LibraryLayout
from natureai_next.application.maintenance_inventory import (
    MaintenanceInventory,
    PackageEntry,
    StorageEntry,
)
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseRegistry


class SqliteMaintenanceInventoryReader:
    """Inspect storage read-only without activating optional subsystems."""

    def __init__(
        self,
        *,
        layout: LibraryLayout,
        application_storage: tuple[tuple[str, str, Path, bool], ...],
        subsystem_registry: SubsystemDatabaseRegistry,
    ) -> None:
        self._layout = layout
        self._application_storage = application_storage
        self._subsystems = subsystem_registry

    def inspect(self) -> MaintenanceInventory:
        storage = tuple(self._storage_entries())
        packages = (*self._map_packages(), *self._taxonomy_packages())
        return MaintenanceInventory(storage, packages)

    def _storage_entries(self) -> Iterable[StorageEntry]:
        categories = (
            ("originals", "Managed originals", self._layout.managed_originals, True),
            ("sidecars", "Sidecars", self._layout.sidecars, True),
            ("thumbnails", "Thumbnail cache", self._layout.thumbnails, False),
            ("previews", "Preview cache", self._layout.previews, False),
            ("indexes", "Vector indexes", self._layout.vector_indexes, False),
            ("temporary", "Temporary workspace", self._layout.temp, False),
            ("backups", "Library backups", self._layout.backups, True),
            *self._application_storage,
        )
        for key, title, path, authoritative in categories:
            size, count = self._path_usage(path)
            yield StorageEntry(key, title, path, size, count, authoritative)

    @staticmethod
    def _path_usage(path: Path) -> tuple[int, int]:
        if not path.exists() or path.is_symlink():
            return 0, 0
        if path.is_file():
            try:
                return path.stat().st_size, 1
            except OSError:
                return 0, 0
        total = 0
        count = 0
        stack = [path]
        while stack:
            current = stack.pop()
            try:
                children = tuple(current.iterdir())
            except OSError:
                continue
            for child in children:
                if child.is_symlink():
                    continue
                try:
                    if child.is_dir():
                        stack.append(child)
                    elif child.is_file():
                        total += child.stat().st_size
                        count += 1
                except OSError:
                    continue
        return total, count

    def _map_packages(self) -> tuple[PackageEntry, ...]:
        descriptor = self._subsystems.descriptor("maps.offline")
        if not descriptor.database_path.is_file():
            return ()
        try:
            connection = sqlite3.connect(
                f"file:{descriptor.database_path.as_posix()}?mode=ro", uri=True
            )
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    "SELECT public_id,package_name,package_version,enabled,status,"
                    "COALESCE(verified_size_bytes,0) AS size_bytes,data_license,attribution,package_path "
                    "FROM map_packages ORDER BY package_name,package_version DESC"
                ).fetchall()
            finally:
                connection.close()
        except (OSError, sqlite3.DatabaseError):
            return ()
        return tuple(
            PackageEntry(
                subsystem="maps.offline",
                public_id=str(row["public_id"]),
                name=str(row["package_name"]),
                version=str(row["package_version"]),
                enabled=bool(row["enabled"]),
                status=str(row["status"]),
                size_bytes=int(row["size_bytes"] or 0),
                license_name=str(row["data_license"] or ""),
                attribution=str(row["attribution"] or ""),
                path=Path(str(row["package_path"])),
            )
            for row in rows
        )

    def _taxonomy_packages(self) -> tuple[PackageEntry, ...]:
        descriptor = self._subsystems.descriptor("taxonomy.reference")
        if not descriptor.database_path.is_file():
            return ()
        try:
            connection = sqlite3.connect(
                f"file:{descriptor.database_path.as_posix()}?mode=ro", uri=True
            )
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    "SELECT public_id,source_name,source_version,enabled,active,license_name,attribution "
                    "FROM taxonomy_datasets ORDER BY source_name,installed_at_us DESC"
                ).fetchall()
            finally:
                connection.close()
        except (OSError, sqlite3.DatabaseError):
            return ()
        return tuple(
            PackageEntry(
                subsystem="taxonomy.reference",
                public_id=str(row["public_id"]),
                name=str(row["source_name"]),
                version=str(row["source_version"]),
                enabled=bool(row["enabled"]),
                status="active" if bool(row["active"]) else "installed",
                size_bytes=0,
                license_name=str(row["license_name"] or ""),
                attribution=str(row["attribution"] or ""),
            )
            for row in rows
        )
