"""Initial offline-map package catalog schema."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    1,
    "offline_map_catalog",
    """
CREATE TABLE map_packages (
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    provider_key TEXT NOT NULL,
    package_name TEXT NOT NULL,
    package_version TEXT NOT NULL,
    format TEXT NOT NULL CHECK(format IN ('mbtiles','vector-mbtiles','pmtiles','vector_bundle','raster_bundle','other')),
    package_path TEXT NOT NULL UNIQUE,
    min_zoom INTEGER,
    max_zoom INTEGER,
    west REAL,
    south REAL,
    east REAL,
    north REAL,
    checksum_sha256 TEXT,
    attribution TEXT NOT NULL DEFAULT '',
    installed_at_us INTEGER NOT NULL,
    last_verified_at_us INTEGER,
    status TEXT NOT NULL DEFAULT 'installed' CHECK(status IN ('installed','missing','invalid','disabled'))
);
CREATE INDEX ix_map_packages_provider ON map_packages(provider_key, status);
CREATE INDEX ix_map_packages_bounds ON map_packages(west, south, east, north);

CREATE TABLE geocoding_packages (
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    provider_key TEXT NOT NULL,
    package_name TEXT NOT NULL,
    package_version TEXT NOT NULL,
    package_path TEXT NOT NULL UNIQUE,
    checksum_sha256 TEXT,
    installed_at_us INTEGER NOT NULL,
    last_verified_at_us INTEGER,
    status TEXT NOT NULL DEFAULT 'installed' CHECK(status IN ('installed','missing','invalid','disabled'))
);
""",
)
