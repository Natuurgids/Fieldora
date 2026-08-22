"""Server search projection subsystem."""

from pathlib import Path

from natureai_next.infrastructure.database.migrations.core import Migration
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseDescriptor

SERVER_SEARCH_SUBSYSTEM_KEY = "server.search"
SERVER_SEARCH_MIGRATIONS = (
    Migration(
        1,
        "rebuildable server search projection",
        """
        CREATE TABLE IF NOT EXISTS search_documents(
            row_id INTEGER PRIMARY KEY,resource_type TEXT NOT NULL,
            resource_id TEXT NOT NULL,organization_id TEXT NOT NULL,
            project_id TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,
            UNIQUE(resource_type,resource_id)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
            title,body,content='search_documents',content_rowid='row_id'
        );
        """,
    ),
)


def server_search_descriptor(database_path: Path) -> SubsystemDatabaseDescriptor:
    return SubsystemDatabaseDescriptor(
        SERVER_SEARCH_SUBSYSTEM_KEY, database_path, SERVER_SEARCH_MIGRATIONS, False
    )
