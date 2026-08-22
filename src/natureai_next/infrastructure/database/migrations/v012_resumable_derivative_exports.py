"""Extend the export journal for restart-safe derivative packages."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE export_plans_v12(
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    export_kind TEXT NOT NULL CHECK(export_kind IN ('original_files','derivatives')),
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
INSERT INTO export_plans_v12
SELECT id,public_id,export_kind,schema_version,destination_path,plan_json,state,created_at_us,
       modified_at_us,completed_at_us,manifest_path,manifest_sha256,error_text
FROM export_plans;

CREATE TABLE export_plan_items_v12(
    id INTEGER PRIMARY KEY,
    export_plan_id INTEGER NOT NULL REFERENCES export_plans_v12(id) ON DELETE CASCADE,
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
    item_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(item_json)),
    output_pixel_width INTEGER CHECK(output_pixel_width IS NULL OR output_pixel_width > 0),
    output_pixel_height INTEGER CHECK(output_pixel_height IS NULL OR output_pixel_height > 0),
    xmp_relative_path TEXT,
    xmp_size_bytes INTEGER CHECK(xmp_size_bytes IS NULL OR xmp_size_bytes >= 0),
    xmp_sha256 TEXT CHECK(xmp_sha256 IS NULL OR (length(xmp_sha256)=64 AND xmp_sha256 NOT GLOB '*[^0-9a-f]*')),
    UNIQUE(export_plan_id,asset_public_id),
    UNIQUE(export_plan_id,relative_output_path),
    UNIQUE(export_plan_id,item_order)
);
INSERT INTO export_plan_items_v12(
    id,export_plan_id,asset_public_id,item_order,source_path,source_size_bytes,source_sha256,
    relative_output_path,state,attempt_count,output_size_bytes,output_sha256,error_text,modified_at_us
)
SELECT id,export_plan_id,asset_public_id,item_order,source_path,source_size_bytes,source_sha256,
       relative_output_path,state,attempt_count,output_size_bytes,output_sha256,error_text,modified_at_us
FROM export_plan_items;

DROP TABLE export_plan_items;
DROP TABLE export_plans;
ALTER TABLE export_plans_v12 RENAME TO export_plans;
ALTER TABLE export_plan_items_v12 RENAME TO export_plan_items;
CREATE INDEX ix_export_plans_state ON export_plans(state,created_at_us,id);
CREATE INDEX ix_export_plan_items_state ON export_plan_items(export_plan_id,state,item_order,id);
"""

MIGRATION = Migration(12, "resumable_derivative_exports", SQL)
