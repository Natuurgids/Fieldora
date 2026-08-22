"""Fieldora Science subsystem database registration."""

from __future__ import annotations

from pathlib import Path

from natureai_next.infrastructure.database.migrations.core import Migration
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseDescriptor


SCIENCE_SUBSYSTEM_KEY = "science.fieldora"

SCIENCE_MIGRATIONS = (
    Migration(
        1,
        "science subsystem ownership",
        """
        CREATE TABLE IF NOT EXISTS science_schema_metadata(
            id INTEGER PRIMARY KEY CHECK(id=1),
            schema_family TEXT NOT NULL,
            clean_start INTEGER NOT NULL CHECK(clean_start IN (0,1))
        );
        INSERT OR IGNORE INTO science_schema_metadata(id,schema_family,clean_start)
        VALUES(1,'fieldora-science',1);
        """,
    ),
    Migration(
        2,
        "incremental science records",
        """
        CREATE TABLE IF NOT EXISTS science_state(
            id INTEGER PRIMARY KEY CHECK(id=1),
            revision INTEGER NOT NULL CHECK(revision >= 0)
        );
        INSERT OR IGNORE INTO science_state(id,revision) VALUES(1,0);
        CREATE TABLE IF NOT EXISTS science_records(
            collection_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            record_revision INTEGER NOT NULL CHECK(record_revision >= 1),
            updated_at_us INTEGER NOT NULL,
            PRIMARY KEY(collection_name,record_id)
        );
        CREATE INDEX IF NOT EXISTS ix_science_records_collection
            ON science_records(collection_name,updated_at_us,record_id);
        """,
    ),
)


def science_descriptor(database_path: Path) -> SubsystemDatabaseDescriptor:
    return SubsystemDatabaseDescriptor(
        key=SCIENCE_SUBSYSTEM_KEY,
        database_path=database_path,
        migrations=SCIENCE_MIGRATIONS,
        optional=True,
    )
