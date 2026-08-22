"""Durable contribution acknowledgment and conflict resolution."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    34,
    "contribution_review",
    """
CREATE TABLE sync_contribution_acknowledgments(
    acknowledgment_id TEXT PRIMARY KEY,
    enrollment_id TEXT NOT NULL REFERENCES sync_project_enrollments(enrollment_id) ON DELETE CASCADE,
    enrollment_revision INTEGER NOT NULL CHECK(enrollment_revision>=0),
    license_id TEXT NOT NULL,
    terms_sha256 TEXT NOT NULL CHECK(length(terms_sha256)=64),
    acknowledged_by TEXT NOT NULL,
    acknowledged_at_utc TEXT NOT NULL,
    UNIQUE(enrollment_id,enrollment_revision,license_id,terms_sha256)
);
ALTER TABLE sync_conflicts ADD COLUMN resolution TEXT NOT NULL DEFAULT ''
CHECK(resolution IN ('','keep_local','accept_remote','manual'));
ALTER TABLE sync_conflicts ADD COLUMN resolved_payload_json TEXT
CHECK(resolved_payload_json IS NULL OR json_valid(resolved_payload_json));
""",
)
