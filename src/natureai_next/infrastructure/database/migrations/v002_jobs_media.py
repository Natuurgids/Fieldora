"""Durable worker leases and derivative cache manifests."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE jobs ADD COLUMN cancellation_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancellation_requested IN (0,1));
ALTER TABLE jobs ADD COLUMN pause_requested INTEGER NOT NULL DEFAULT 0 CHECK(pause_requested IN (0,1));
ALTER TABLE jobs ADD COLUMN lease_owner TEXT;
ALTER TABLE jobs ADD COLUMN lease_expires_at_us INTEGER;
CREATE INDEX ix_jobs_claim ON jobs(state,resource_class,priority DESC,retry_at_us,created_at_us);
CREATE INDEX ix_jobs_lease ON jobs(state,lease_expires_at_us);
CREATE TABLE derivative_cache_entries(
    id INTEGER PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
    source_file_instance_id INTEGER NOT NULL REFERENCES file_instances(id) ON DELETE CASCADE,
    derivative_kind TEXT NOT NULL CHECK(derivative_kind IN ('thumbnail','preview')),
    cache_key TEXT NOT NULL UNIQUE,
    relative_path TEXT NOT NULL UNIQUE,
    source_sha256 TEXT,
    source_size INTEGER NOT NULL,
    source_modified_at_us INTEGER,
    renderer_identity TEXT NOT NULL,
    parameters_json TEXT NOT NULL CHECK(json_valid(parameters_json)),
    output_sha256 TEXT NOT NULL,
    output_size INTEGER NOT NULL,
    pixel_width INTEGER NOT NULL,
    pixel_height INTEGER NOT NULL,
    created_at_us INTEGER NOT NULL,
    validated_at_us INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('valid','stale','missing','corrupt')),
    UNIQUE(source_file_instance_id,derivative_kind,renderer_identity,parameters_json)
);
CREATE INDEX ix_derivative_asset_kind ON derivative_cache_entries(asset_id,derivative_kind,state);
"""
MIGRATION = Migration(2, "jobs_media_pipeline", SQL)
