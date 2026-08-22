"""Phase E desktop endpoint, device, and project enrollment state."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    31,
    "desktop_synchronization",
    """
CREATE TABLE sync_accounts(
    account_id TEXT PRIMARY KEY,
    endpoint_url TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE TABLE sync_devices(
    device_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES sync_accounts(account_id) ON DELETE CASCADE,
    server_device_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    registered_at_utc TEXT NOT NULL,
    revoked_at_utc TEXT NOT NULL DEFAULT '',
    UNIQUE(account_id,server_device_id)
);
CREATE TABLE sync_project_enrollments(
    enrollment_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES sync_accounts(account_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('active','expired','revoked')),
    rights_json TEXT NOT NULL CHECK(json_valid(rights_json)),
    expires_at_utc TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision>=0),
    acknowledged_at_utc TEXT NOT NULL,
    UNIQUE(account_id,project_id)
);
CREATE INDEX ix_sync_enrollments_account_state
ON sync_project_enrollments(account_id,state,project_id);
""",
)

