"""Aperture integration registry application service."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


@dataclass(frozen=True, slots=True)
class IntegrationSystem:
    integration_id: str
    display_name: str
    provider_type: str
    version: str | None
    enabled: bool
    availability_state: str
    database_relative_path: str | None
    capabilities: tuple[str, ...]
    last_error_summary: str | None


class IntegrationRegistryService:
    """Controls optional processing while preserving canonical results."""

    def __init__(self, database_path: Path) -> None:
        self._factory = SqliteConnectionFactory(database_path)

    def list(self) -> tuple[IntegrationSystem, ...]:
        with self._factory.connect(read_only=True) as connection:
            rows = connection.execute(
                "SELECT integration_id,display_name,provider_type,version,enabled,availability_state,"
                "database_relative_path,last_error_summary FROM integration_systems ORDER BY display_name"
            ).fetchall()
            result = []
            for row in rows:
                capabilities = connection.execute(
                    "SELECT capability_id FROM integration_capabilities "
                    "WHERE integration_id=? AND enabled=1 ORDER BY capability_id",
                    (row[0],),
                ).fetchall()
                result.append(
                    IntegrationSystem(
                        str(row[0]),
                        str(row[1]),
                        str(row[2]),
                        row[3],
                        bool(row[4]),
                        str(row[5]),
                        row[6],
                        tuple(str(c[0]) for c in capabilities),
                        row[7],
                    )
                )
        return tuple(result)

    def set_enabled(self, integration_id: str, enabled: bool) -> None:
        now = time.time_ns() // 1000
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE integration_systems SET enabled=?,last_started_at_us=CASE WHEN ?=1 THEN ? ELSE last_started_at_us END,"
                "last_stopped_at_us=CASE WHEN ?=0 THEN ? ELSE last_stopped_at_us END WHERE integration_id=?",
                (int(enabled), int(enabled), now, int(enabled), now, integration_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(integration_id)
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
