"""Permit direct vector MBTiles map resources."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    4,
    "vector_mbtiles_resources",
    """
PRAGMA foreign_keys=OFF;
ALTER TABLE map_packages RENAME TO map_packages_old;
CREATE TABLE map_packages (
    id INTEGER PRIMARY KEY, public_id TEXT NOT NULL UNIQUE, provider_key TEXT NOT NULL,
    package_name TEXT NOT NULL, package_version TEXT NOT NULL,
    format TEXT NOT NULL CHECK(format IN ('mbtiles','vector-mbtiles','pmtiles','vector_bundle','raster_bundle','other')),
    package_path TEXT NOT NULL UNIQUE, min_zoom INTEGER, max_zoom INTEGER, west REAL, south REAL, east REAL, north REAL,
    checksum_sha256 TEXT, attribution TEXT NOT NULL DEFAULT '', installed_at_us INTEGER NOT NULL, last_verified_at_us INTEGER,
    status TEXT NOT NULL DEFAULT 'installed' CHECK(status IN ('installed','missing','invalid','disabled')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), verification_message TEXT NOT NULL DEFAULT '',
    verified_size_bytes INTEGER, observed_checksum_sha256 TEXT, provider_metadata_json TEXT NOT NULL DEFAULT '{}',
    tile_scheme TEXT NOT NULL DEFAULT 'tms' CHECK(tile_scheme IN ('tms','xyz')), data_license TEXT NOT NULL DEFAULT '',
    attribution_url TEXT NOT NULL DEFAULT ''
);
INSERT INTO map_packages SELECT * FROM map_packages_old;
DROP TABLE map_packages_old;
CREATE INDEX ix_map_packages_provider ON map_packages(provider_key,status);
CREATE INDEX ix_map_packages_bounds ON map_packages(west,south,east,north);
CREATE INDEX ix_map_packages_enabled_status ON map_packages(enabled,status,provider_key);
CREATE INDEX ix_map_packages_provider_format ON map_packages(provider_key,format);
PRAGMA foreign_keys=ON;
""",
)
