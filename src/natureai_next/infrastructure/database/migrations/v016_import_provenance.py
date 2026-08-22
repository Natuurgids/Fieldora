"""Version 2 import-session provenance without changing Version 1 import semantics."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE import_plans ADD COLUMN source_root TEXT;
ALTER TABLE import_plans ADD COLUMN source_volume_label TEXT;
ALTER TABLE import_plans ADD COLUMN source_volume_serial TEXT;
ALTER TABLE import_plans ADD COLUMN application_version TEXT;
ALTER TABLE import_plans ADD COLUMN notes TEXT;

ALTER TABLE import_plan_items ADD COLUMN original_filename TEXT;
ALTER TABLE import_plan_items ADD COLUMN original_relative_path TEXT;
ALTER TABLE import_plan_items ADD COLUMN source_created_at_us INTEGER;
ALTER TABLE import_plan_items ADD COLUMN capture_latitude REAL CHECK(capture_latitude IS NULL OR (capture_latitude>=-90 AND capture_latitude<=90));
ALTER TABLE import_plan_items ADD COLUMN capture_longitude REAL CHECK(capture_longitude IS NULL OR (capture_longitude>=-180 AND capture_longitude<=180));
ALTER TABLE import_plan_items ADD COLUMN capture_altitude_m REAL;
ALTER TABLE import_plan_items ADD COLUMN location_source TEXT;
ALTER TABLE import_plan_items ADD COLUMN metadata_extraction_state TEXT NOT NULL DEFAULT 'pending'
 CHECK(metadata_extraction_state IN ('pending','succeeded','failed','not_available'));

CREATE INDEX ix_import_plans_source_volume ON import_plans(source_volume_serial,created_at_us,id);
CREATE INDEX ix_import_plan_items_location ON import_plan_items(capture_latitude,capture_longitude)
 WHERE capture_latitude IS NOT NULL AND capture_longitude IS NOT NULL;
"""

MIGRATION = Migration(16, "import_session_provenance", SQL)
