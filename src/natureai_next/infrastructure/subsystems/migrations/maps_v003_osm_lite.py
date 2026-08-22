"""OpenStreetMap-compatible lightweight offline tile support."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    3,
    "osm_lite_offline_tiles",
    """
ALTER TABLE map_packages ADD COLUMN tile_scheme TEXT NOT NULL DEFAULT 'tms'
    CHECK(tile_scheme IN ('tms','xyz'));
ALTER TABLE map_packages ADD COLUMN data_license TEXT NOT NULL DEFAULT '';
ALTER TABLE map_packages ADD COLUMN attribution_url TEXT NOT NULL DEFAULT '';
CREATE INDEX ix_map_packages_provider_format ON map_packages(provider_key, format);
""",
)
