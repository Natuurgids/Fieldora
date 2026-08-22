"""Durable Phase E resumable media transfer checkpoints."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    33,
    "resumable_media_sync",
    """
CREATE TABLE sync_media_transfers(
    transfer_id TEXT PRIMARY KEY,
    enrollment_id TEXT NOT NULL REFERENCES sync_project_enrollments(enrollment_id) ON DELETE CASCADE,
    media_id TEXT NOT NULL,
    destination_path TEXT NOT NULL,
    expected_size INTEGER NOT NULL CHECK(expected_size>=0),
    expected_sha256 TEXT NOT NULL CHECK(length(expected_sha256)=64),
    etag TEXT NOT NULL,
    offset INTEGER NOT NULL DEFAULT 0 CHECK(offset>=0 AND offset<=expected_size),
    state TEXT NOT NULL CHECK(state IN ('pending','transferring','complete','failed')),
    UNIQUE(enrollment_id,media_id,destination_path)
);
""",
)
