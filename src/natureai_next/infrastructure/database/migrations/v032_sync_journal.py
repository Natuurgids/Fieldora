"""Durable revision synchronization journal, cursors, and conflicts."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    32,
    "sync_journal",
    """
CREATE TABLE sync_outbox(
    change_id TEXT PRIMARY KEY,
    enrollment_id TEXT NOT NULL REFERENCES sync_project_enrollments(enrollment_id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL UNIQUE,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    base_revision INTEGER NOT NULL CHECK(base_revision>=0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    tombstone INTEGER NOT NULL CHECK(tombstone IN (0,1)),
    state TEXT NOT NULL CHECK(state IN ('pending','inflight','applied','retry','conflict','rejected')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count>=0),
    next_attempt_at_utc TEXT NOT NULL DEFAULT '',
    lease_until_utc TEXT NOT NULL DEFAULT ''
);
CREATE INDEX ix_sync_outbox_claim
ON sync_outbox(state,next_attempt_at_utc,lease_until_utc,change_id);
CREATE TABLE sync_inbox(
    change_id TEXT PRIMARY KEY,
    enrollment_id TEXT NOT NULL REFERENCES sync_project_enrollments(enrollment_id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL UNIQUE,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    base_revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    tombstone INTEGER NOT NULL CHECK(tombstone IN (0,1)),
    applied_at_utc TEXT NOT NULL DEFAULT ''
);
CREATE TABLE sync_cursors(
    enrollment_id TEXT PRIMARY KEY REFERENCES sync_project_enrollments(enrollment_id) ON DELETE CASCADE,
    cursor TEXT NOT NULL
);
CREATE TABLE sync_conflicts(
    conflict_id TEXT PRIMARY KEY,
    enrollment_id TEXT NOT NULL REFERENCES sync_project_enrollments(enrollment_id) ON DELETE CASCADE,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    local_revision INTEGER NOT NULL,
    remote_revision INTEGER NOT NULL,
    local_payload_json TEXT NOT NULL CHECK(json_valid(local_payload_json)),
    remote_payload_json TEXT NOT NULL CHECK(json_valid(remote_payload_json)),
    created_at_utc TEXT NOT NULL,
    resolved_at_utc TEXT NOT NULL DEFAULT ''
);
""",
)
