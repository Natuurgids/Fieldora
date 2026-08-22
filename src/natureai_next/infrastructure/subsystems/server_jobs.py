"""Durable server-jobs subsystem."""

from pathlib import Path

from natureai_next.infrastructure.database.migrations.core import Migration
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseDescriptor

SERVER_JOBS_SUBSYSTEM_KEY = "server.jobs"
SERVER_JOBS_MIGRATIONS = (
    Migration(
        1,
        "durable leased server jobs",
        """
        CREATE TABLE IF NOT EXISTS server_jobs(
            job_id TEXT PRIMARY KEY,job_type TEXT NOT NULL,subject_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,project_id TEXT NOT NULL,status TEXT NOT NULL,
            payload_json TEXT NOT NULL,result_json TEXT NOT NULL,attempts INTEGER NOT NULL,
            lease_until_utc TEXT NOT NULL,created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        """,
    ),
    Migration(
        2,
        "fenced multi-worker leases",
        """
        ALTER TABLE server_jobs ADD COLUMN lease_owner TEXT NOT NULL DEFAULT '';
        ALTER TABLE server_jobs ADD COLUMN lease_token TEXT NOT NULL DEFAULT '';
        CREATE INDEX ix_server_jobs_claim
        ON server_jobs(status,lease_until_utc,attempts,created_at_utc);
        """,
    ),
)


def server_jobs_descriptor(database_path: Path) -> SubsystemDatabaseDescriptor:
    return SubsystemDatabaseDescriptor(
        SERVER_JOBS_SUBSYSTEM_KEY, database_path, SERVER_JOBS_MIGRATIONS, True
    )
