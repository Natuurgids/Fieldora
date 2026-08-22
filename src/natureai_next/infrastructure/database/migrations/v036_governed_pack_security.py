"""Encrypted governed-pack security and revocation registry."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    36,
    "governed_pack_security",
    """
CREATE TABLE sync_governed_pack_security(
    pack_id TEXT PRIMARY KEY,
    enrollment_id TEXT NOT NULL REFERENCES sync_project_enrollments(enrollment_id) ON DELETE CASCADE,
    envelope_path TEXT NOT NULL,
    key_ref TEXT NOT NULL UNIQUE,
    expires_at_utc TEXT NOT NULL,
    signing_key_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','expired','revoked'))
);
CREATE INDEX ix_governed_pack_expiry
ON sync_governed_pack_security(state,expires_at_utc,pack_id);
""",
)
