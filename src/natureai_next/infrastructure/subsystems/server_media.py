"""Governed server-media registry subsystem."""

from pathlib import Path

from natureai_next.infrastructure.database.migrations.core import Migration
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseDescriptor

SERVER_MEDIA_SUBSYSTEM_KEY = "server.media"
SERVER_MEDIA_MIGRATIONS = (
    Migration(
        1,
        "governed media registry",
        """
        CREATE TABLE IF NOT EXISTS governed_media(
            media_id TEXT PRIMARY KEY,relative_path TEXT NOT NULL UNIQUE,
            organization_id TEXT NOT NULL,project_id TEXT NOT NULL,
            mime_type TEXT NOT NULL,size_bytes INTEGER NOT NULL,sha256 TEXT NOT NULL
        );
        """,
    ),
    Migration(
        2,
        "restart safe governed uploads",
        """
        CREATE TABLE IF NOT EXISTS governed_uploads(
            upload_id TEXT PRIMARY KEY,subject_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,project_id TEXT NOT NULL,
            filename TEXT NOT NULL,mime_type TEXT NOT NULL,
            expected_size INTEGER NOT NULL,expected_sha256 TEXT NOT NULL,
            received_bytes INTEGER NOT NULL
        );
        """,
    ),
)


def server_media_descriptor(database_path: Path) -> SubsystemDatabaseDescriptor:
    return SubsystemDatabaseDescriptor(
        SERVER_MEDIA_SUBSYSTEM_KEY, database_path, SERVER_MEDIA_MIGRATIONS, True
    )
