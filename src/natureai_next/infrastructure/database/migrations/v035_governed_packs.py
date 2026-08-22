"""Isolated desktop registry for governed project data packs."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    35,
    "governed_packs",
    """
CREATE TABLE sync_governed_packs(
    enrollment_id TEXT PRIMARY KEY REFERENCES sync_project_enrollments(enrollment_id) ON DELETE CASCADE,
    pack_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version>0),
    payload_path TEXT NOT NULL,
    package_sha256 TEXT NOT NULL CHECK(length(package_sha256)=64),
    state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','expired','revoked','removing'))
);
""",
)
