"""Visibility settings for independent Fieldora Science workspaces."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


SCIENCE_CAPABILITIES = (
    ("science.projects", "Science Projects", 10),
    ("science.dossiers", "Science Dossiers", 20),
    ("science.animals", "Animal Records", 30),
    ("science.plants", "Plant & Flower Records", 40),
    ("science.marine", "Marine & Freshwater Science", 50),
    ("science.maritime", "Maritime Operations", 60),
    ("science.other_artifacts", "Other Science Artifacts", 70),
    ("science.whiteboard", "Excalidraw Whiteboards", 80),
    ("science.calendar", "Science Calendar", 90),
    ("workspace.operations", "Asset & Equipment Operations", 100),
    ("workspace.measurements", "Measurements & Protocols", 110),
    ("workspace.ai_chat", "AI Chat & MCP", 120),
    ("workspace.ai_admin", "AI Platform Administration", 130),
    ("workspace.governance", "Administration Governance", 140),
    ("workspace.reference_data", "Research Reference Data", 150),
    ("workspace.platform_parity", "Platform Parity", 160),
)


@dataclass(frozen=True, slots=True)
class ScienceCapability:
    capability_id: str
    display_name: str
    enabled: bool
    display_order: int


class ScienceCapabilityService:
    def __init__(self, database_path: Path) -> None:
        self._path = database_path
        self._ensure()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _ensure(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS science_capabilities(
                    capability_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                    display_order INTEGER NOT NULL,
                    updated_at_us INTEGER NOT NULL
                )
                """
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO science_capabilities
                    (capability_id,display_name,enabled,display_order,updated_at_us)
                VALUES(?,?,1,?,?)
                """,
                [
                    (key, name, order, time.time_ns() // 1000)
                    for key, name, order in SCIENCE_CAPABILITIES
                ],
            )

    def list(self) -> tuple[ScienceCapability, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT capability_id,display_name,enabled,display_order "
                "FROM science_capabilities ORDER BY display_order"
            ).fetchall()
        return tuple(
            ScienceCapability(str(row[0]), str(row[1]), bool(row[2]), int(row[3]))
            for row in rows
        )

    def set_enabled(self, capability_id: str, enabled: bool) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE science_capabilities SET enabled=?,updated_at_us=? "
                "WHERE capability_id=?",
                (int(enabled), time.time_ns() // 1000, capability_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(capability_id)
