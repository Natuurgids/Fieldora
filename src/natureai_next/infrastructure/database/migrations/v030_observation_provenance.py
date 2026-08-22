"""Build 28.4 observation provenance and multi-source resolution."""
from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE asset_storage_locations ADD COLUMN provenance_role TEXT NOT NULL DEFAULT 'follow_up'
    CHECK(provenance_role IN ('initial','follow_up','managed_copy','derived'));
ALTER TABLE asset_storage_locations ADD COLUMN discovered_at_us INTEGER;

-- Existing libraries: the oldest source location is the immutable initial observation.
UPDATE asset_storage_locations
SET provenance_role='initial',
    discovered_at_us=COALESCE(discovered_at_us,created_at_us)
WHERE role='source'
  AND id IN (SELECT MIN(id) FROM asset_storage_locations WHERE role='source' GROUP BY asset_id);
UPDATE asset_storage_locations
SET provenance_role='managed_copy',
    discovered_at_us=COALESCE(discovered_at_us,created_at_us)
WHERE role='aperture_master';
UPDATE asset_storage_locations
SET discovered_at_us=COALESCE(discovered_at_us,created_at_us)
WHERE discovered_at_us IS NULL;

CREATE UNIQUE INDEX ux_asset_one_initial_observation
ON asset_storage_locations(asset_id) WHERE provenance_role='initial';
CREATE INDEX ix_asset_storage_provenance
ON asset_storage_locations(asset_id,provenance_role,discovered_at_us,id);
"""

MIGRATION = Migration(30, "build28_4_observation_provenance", SQL)
