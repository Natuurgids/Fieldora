"""Governed server-exports subsystem."""

from pathlib import Path

from natureai_next.infrastructure.database.migrations.core import Migration
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseDescriptor

SERVER_EXPORTS_SUBSYSTEM_KEY = "server.exports"
SERVER_EXPORTS_MIGRATIONS = (
    Migration(
        1,
        "governed expiring project exports",
        """
        CREATE TABLE IF NOT EXISTS governed_exports(
            export_id TEXT PRIMARY KEY,job_id TEXT NOT NULL UNIQUE,
            subject_id TEXT NOT NULL,organization_id TEXT NOT NULL,
            project_id TEXT NOT NULL,filename TEXT NOT NULL,
            relative_path TEXT NOT NULL UNIQUE,size_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL,created_at_utc TEXT NOT NULL,
            expires_at_utc TEXT NOT NULL
        );
        """,
    ),
    Migration(
        2,
        "revocable export lifecycle and purge audit",
        """
        ALTER TABLE governed_exports ADD COLUMN
            revoked_at_utc TEXT NOT NULL DEFAULT '';
        ALTER TABLE governed_exports ADD COLUMN
            purged_at_utc TEXT NOT NULL DEFAULT '';
        """,
    ),
    Migration(
        3,
        "detached Ed25519 export attestations",
        """
        ALTER TABLE governed_exports ADD COLUMN
            signing_key_id TEXT NOT NULL DEFAULT '';
        ALTER TABLE governed_exports ADD COLUMN
            signature_base64 TEXT NOT NULL DEFAULT '';
        """,
    ),
)


def server_exports_descriptor(database_path: Path) -> SubsystemDatabaseDescriptor:
    return SubsystemDatabaseDescriptor(
        SERVER_EXPORTS_SUBSYSTEM_KEY, database_path, SERVER_EXPORTS_MIGRATIONS, True
    )
