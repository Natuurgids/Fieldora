"""Registry and lifecycle for isolated optional subsystem databases."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from natureai_next.domain.subsystems import SubsystemState
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.integrity import check_integrity
from natureai_next.infrastructure.database.migrations.core import (
    Migration,
    MigrationError,
    MigrationRunner,
)
from natureai_next.infrastructure.database.settings import SqliteSettings


@dataclass(frozen=True, slots=True)
class SubsystemDatabaseDescriptor:
    key: str
    database_path: Path
    migrations: tuple[Migration, ...]
    optional: bool = True

    @property
    def schema_version(self) -> int:
        return len(self.migrations)


@dataclass(frozen=True, slots=True)
class SubsystemHealth:
    key: str
    state: SubsystemState
    database_path: Path
    schema_version: int
    message: str = ""


class SubsystemDatabaseRegistry:
    """Owns descriptors but opens optional databases only on explicit activation."""

    def __init__(
        self,
        descriptors: Iterable[SubsystemDatabaseDescriptor],
        application_version: str,
        settings: SqliteSettings | None = None,
    ) -> None:
        items = tuple(descriptors)
        duplicate_keys = {item.key for item in items if sum(x.key == item.key for x in items) > 1}
        if duplicate_keys:
            raise ValueError(f"duplicate subsystem keys: {', '.join(sorted(duplicate_keys))}")
        self._descriptors = {item.key: item for item in items}
        self._application_version = application_version
        self._settings = settings or SqliteSettings()
        self._active_factories: dict[str, SqliteConnectionFactory] = {}

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    def descriptor(self, key: str) -> SubsystemDatabaseDescriptor:
        try:
            return self._descriptors[key]
        except KeyError as exc:
            raise KeyError(f"unknown subsystem database: {key}") from exc

    def is_active(self, key: str) -> bool:
        return key in self._active_factories

    def activate(self, key: str) -> SqliteConnectionFactory:
        """Create/open and migrate a subsystem database on explicit request."""
        if key in self._active_factories:
            return self._active_factories[key]
        descriptor = self.descriptor(key)
        factory = SqliteConnectionFactory(descriptor.database_path, self._settings)
        connection = factory.connect()
        try:
            try:
                MigrationRunner(descriptor.migrations, self._application_version).apply(connection)
            except MigrationError as exc:
                # V4 is a clean-start baseline. Subsystem databases live under the
                # application data root and may survive replacement of a development
                # build even when the selected Aperture Library is new. Never mutate an
                # incompatible database in place: preserve it for diagnostics, then
                # recreate the subsystem using the current immutable schema.
                connection.close()
                self._archive_incompatible_database(descriptor.database_path, str(exc))
                connection = factory.connect()
                MigrationRunner(descriptor.migrations, self._application_version).apply(connection)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS subsystem_info ("
                "id INTEGER PRIMARY KEY CHECK(id=1), subsystem_key TEXT NOT NULL UNIQUE, "
                "current_schema_version INTEGER NOT NULL, application_version TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO subsystem_info(id, subsystem_key, current_schema_version, application_version) "
                "VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "current_schema_version=excluded.current_schema_version, "
                "application_version=excluded.application_version",
                (descriptor.key, descriptor.schema_version, self._application_version),
            )
        finally:
            connection.close()
        self._active_factories[key] = factory
        return factory

    @staticmethod
    def _archive_incompatible_database(database_path: Path, reason: str) -> Path:
        """Preserve an incompatible clean-start subsystem and its SQLite sidecars."""
        import json
        import time

        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        archive = database_path.with_name(
            f"{database_path.name}.incompatible-{stamp}-{time.time_ns() % 1_000_000:06d}"
        )
        database_path.parent.mkdir(parents=True, exist_ok=True)
        if database_path.exists():
            database_path.replace(archive)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(database_path) + suffix)
            if sidecar.exists():
                sidecar.replace(Path(str(archive) + suffix))
        report = Path(str(archive) + ".json")
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "reason": reason,
                    "original_path": str(database_path),
                    "archived_path": str(archive),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return archive

    def deactivate(self, key: str) -> None:
        self._active_factories.pop(key, None)

    def status(self, key: str, *, run_integrity_check: bool = False) -> SubsystemHealth:
        descriptor = self.descriptor(key)
        if not descriptor.database_path.exists():
            return SubsystemHealth(key, SubsystemState.INACTIVE, descriptor.database_path, 0)
        factory = SqliteConnectionFactory(descriptor.database_path, self._settings)
        try:
            connection = factory.connect(read_only=True)
            try:
                row = connection.execute(
                    "SELECT current_schema_version FROM subsystem_info WHERE id=1"
                ).fetchone()
            finally:
                connection.close()
            schema_version = int(row[0]) if row else 0
            if run_integrity_check:
                report = check_integrity(factory, full=False)
                if not report.healthy:
                    return SubsystemHealth(
                        key,
                        SubsystemState.UNHEALTHY,
                        descriptor.database_path,
                        schema_version,
                        "; ".join(report.messages),
                    )
            state = SubsystemState.ACTIVE if self.is_active(key) else SubsystemState.INACTIVE
            return SubsystemHealth(key, state, descriptor.database_path, schema_version)
        except (OSError, sqlite3.DatabaseError) as exc:
            return SubsystemHealth(
                key, SubsystemState.UNAVAILABLE, descriptor.database_path, 0, str(exc)
            )
