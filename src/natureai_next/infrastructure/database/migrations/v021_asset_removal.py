"""Analysis-aware asset removal audit support."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE purge_intents RENAME TO purge_intents_v1;
CREATE TABLE purge_intents(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
 managed_paths_json TEXT NOT NULL CHECK(json_valid(managed_paths_json)),
 state TEXT NOT NULL CHECK(state IN ('pending','files_deleted','completed','failed')),
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL,
 error_text TEXT
);
INSERT INTO purge_intents(id,public_id,asset_id,managed_paths_json,state,created_at_us,modified_at_us,error_text)
SELECT id,public_id,asset_id,managed_paths_json,state,created_at_us,modified_at_us,error_text FROM purge_intents_v1;
DROP TABLE purge_intents_v1;
CREATE INDEX ix_purge_intents_state ON purge_intents(state,created_at_us,id);
"""
MIGRATION = Migration(21, "asset_removal_audit", SQL)
