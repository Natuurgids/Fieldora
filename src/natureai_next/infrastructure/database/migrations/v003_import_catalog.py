"""Import planning and purge-intent persistence."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE import_plans(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 schema_version INTEGER NOT NULL,
 duplicate_policy TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('planned','running','completed','completed_with_errors','cancelled')),
 created_at_us INTEGER NOT NULL,
 completed_at_us INTEGER,
 summary_json TEXT CHECK(summary_json IS NULL OR json_valid(summary_json))
);
CREATE TABLE import_plan_items(
 id INTEGER PRIMARY KEY,
 plan_id INTEGER NOT NULL REFERENCES import_plans(id) ON DELETE CASCADE,
 item_key TEXT NOT NULL,
 source_path TEXT NOT NULL,
 source_size INTEGER NOT NULL CHECK(source_size>=0),
 source_modified_at_us INTEGER NOT NULL,
 sha256 TEXT NOT NULL CHECK(length(sha256)=64),
 fast_fingerprint TEXT NOT NULL,
 storage_policy TEXT NOT NULL CHECK(storage_policy IN ('managed','referenced','hybrid')),
 source_disposition TEXT NOT NULL CHECK(source_disposition IN ('keep','delete_after_verified_copy')),
 decision TEXT NOT NULL,
 existing_asset_id INTEGER REFERENCES assets(id),
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','running','succeeded','skipped','failed')),
 asset_id INTEGER REFERENCES assets(id),
 file_instance_id INTEGER REFERENCES file_instances(id),
 error_code TEXT,
 result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)),
 modified_at_us INTEGER NOT NULL,
 UNIQUE(plan_id,item_key)
);
CREATE INDEX ix_import_plan_items_state ON import_plan_items(plan_id,state,id);
CREATE TABLE purge_intents(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 asset_id INTEGER NOT NULL REFERENCES assets(id),
 managed_paths_json TEXT NOT NULL CHECK(json_valid(managed_paths_json)),
 state TEXT NOT NULL CHECK(state IN ('pending','files_deleted','completed','failed')),
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL,
 error_text TEXT
);
CREATE INDEX ix_purge_intents_state ON purge_intents(state,created_at_us,id);
"""
MIGRATION = Migration(3, "import_catalog", SQL)
