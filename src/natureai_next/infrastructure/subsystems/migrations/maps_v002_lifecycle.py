"""Offline-map package verification and activation lifecycle."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    2,
    "offline_map_package_lifecycle",
    """
ALTER TABLE map_packages ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1));
ALTER TABLE map_packages ADD COLUMN verification_message TEXT NOT NULL DEFAULT '';
ALTER TABLE map_packages ADD COLUMN verified_size_bytes INTEGER;
ALTER TABLE map_packages ADD COLUMN observed_checksum_sha256 TEXT;
ALTER TABLE map_packages ADD COLUMN provider_metadata_json TEXT NOT NULL DEFAULT '{}';
CREATE INDEX ix_map_packages_enabled_status ON map_packages(enabled, status, provider_key);

ALTER TABLE geocoding_packages ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1));
ALTER TABLE geocoding_packages ADD COLUMN verification_message TEXT NOT NULL DEFAULT '';
ALTER TABLE geocoding_packages ADD COLUMN verified_size_bytes INTEGER;
""",
)
