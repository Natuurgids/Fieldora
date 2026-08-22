"""Application service for built-in Library media capabilities."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


@dataclass(frozen=True, slots=True)
class LibraryCapability:
    capability_id: str
    display_name: str
    enabled: bool
    display_order: int


class LibraryCapabilityService:
    """Controls workspace visibility without deleting retained media data."""

    def __init__(self, database_path: Path) -> None:
        self._factory = SqliteConnectionFactory(database_path)

    def list(self) -> tuple[LibraryCapability, ...]:
        with self._factory.connect(read_only=True) as connection:
            rows = connection.execute(
                "SELECT capability_id,display_name,enabled,display_order "
                "FROM library_capabilities ORDER BY display_order"
            ).fetchall()
        return tuple(LibraryCapability(str(r[0]), str(r[1]), bool(r[2]), int(r[3])) for r in rows)

    def enabled(self, capability_id: str) -> bool:
        with self._factory.connect(read_only=True) as connection:
            row = connection.execute(
                "SELECT enabled FROM library_capabilities WHERE capability_id=?", (capability_id,)
            ).fetchone()
        if row is None:
            raise KeyError(capability_id)
        return bool(row[0])

    def set_enabled(self, capability_id: str, enabled: bool) -> None:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE library_capabilities SET enabled=?,updated_at_us=? WHERE capability_id=?",
                (int(enabled), time.time_ns() // 1000, capability_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(capability_id)
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
