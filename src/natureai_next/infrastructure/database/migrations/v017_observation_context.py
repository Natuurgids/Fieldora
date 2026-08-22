"""Explicit observation time and location overrides."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE observations ADD COLUMN observed_at_us INTEGER;
ALTER TABLE observations ADD COLUMN location_id INTEGER REFERENCES locations(id);
ALTER TABLE observations ADD COLUMN time_source TEXT NOT NULL DEFAULT 'derived'
 CHECK(time_source IN ('derived','asset_metadata','user','import','plugin'));
ALTER TABLE observations ADD COLUMN location_source TEXT NOT NULL DEFAULT 'derived'
 CHECK(location_source IN ('derived','asset_metadata','user','import','plugin'));
ALTER TABLE observations ADD COLUMN location_accuracy_m REAL
 CHECK(location_accuracy_m IS NULL OR location_accuracy_m>=0);
CREATE INDEX ix_observations_observed_at ON observations(observed_at_us,id)
 WHERE observed_at_us IS NOT NULL;
CREATE INDEX ix_observations_location ON observations(location_id,id)
 WHERE location_id IS NOT NULL;
"""

MIGRATION = Migration(17, "observation_context", SQL)
