"""Persistent export plans and item-level recovery state."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE export_plans(
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    export_kind TEXT NOT NULL CHECK(export_kind IN ('original_files')),
    schema_version INTEGER NOT NULL,
    destination_path TEXT NOT NULL,
    plan_json TEXT NOT NULL CHECK(json_valid(plan_json)),
    state TEXT NOT NULL CHECK(state IN ('prepared','running','succeeded','failed','cancelled')),
    created_at_us INTEGER NOT NULL,
    modified_at_us INTEGER NOT NULL,
    completed_at_us INTEGER,
    manifest_path TEXT,
    manifest_sha256 TEXT,
    error_text TEXT
);
CREATE INDEX ix_export_plans_state ON export_plans(state,created_at_us,id);

CREATE TABLE export_plan_items(
    id INTEGER PRIMARY KEY,
    export_plan_id INTEGER NOT NULL REFERENCES export_plans(id) ON DELETE CASCADE,
    asset_public_id TEXT NOT NULL,
    item_order INTEGER NOT NULL,
    source_path TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL CHECK(source_size_bytes>=0),
    source_sha256 TEXT,
    relative_output_path TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('pending','running','succeeded','failed','cancelled')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count>=0),
    output_size_bytes INTEGER,
    output_sha256 TEXT,
    error_text TEXT,
    modified_at_us INTEGER NOT NULL,
    UNIQUE(export_plan_id,asset_public_id),
    UNIQUE(export_plan_id,relative_output_path),
    UNIQUE(export_plan_id,item_order)
);
CREATE INDEX ix_export_plan_items_state ON export_plan_items(export_plan_id,state,item_order,id);
"""

MIGRATION = Migration(11, "resumable_exports", SQL)
