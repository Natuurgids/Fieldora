"""Immutable, checksummed SQLite migration framework."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Migration:
    number: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


class MigrationError(RuntimeError):
    pass


class MigrationRunner:
    def __init__(self, migrations: Iterable[Migration], application_version: str) -> None:
        items = tuple(sorted(migrations, key=lambda m: m.number))
        if [m.number for m in items] != list(range(1, len(items) + 1)):
            raise ValueError("migration numbers must be contiguous from 1")
        self.migrations = items
        self.application_version = application_version

    def apply(self, connection: sqlite3.Connection) -> int:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (migration_number INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, applied_at_us INTEGER NOT NULL, application_version TEXT NOT NULL, execution_duration_us INTEGER NOT NULL)"
        )
        applied = {
            int(r[0]): str(r[1])
            for r in connection.execute("SELECT migration_number, checksum FROM schema_migrations")
        }
        for m in self.migrations:
            if m.number in applied:
                if applied[m.number] != m.checksum:
                    raise MigrationError(f"checksum mismatch for migration {m.number}")
                continue
            start = time.perf_counter_ns()
            try:
                connection.executescript("BEGIN IMMEDIATE;\n" + m.sql)
                duration = (time.perf_counter_ns() - start) // 1000
                connection.execute(
                    "INSERT INTO schema_migrations VALUES(?,?,?,?,?,?)",
                    (
                        m.number,
                        m.name,
                        m.checksum,
                        time.time_ns() // 1000,
                        self.application_version,
                        duration,
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        return len(self.migrations)
