"""Build 28.3 references the library-wide device/location registry."""
from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE asset_storage_locations ADD COLUMN device_public_id TEXT;
ALTER TABLE asset_storage_locations ADD COLUMN location_public_id TEXT;
CREATE INDEX ix_asset_storage_locations_device_reference
ON asset_storage_locations(device_public_id,location_public_id,asset_id)
WHERE device_public_id IS NOT NULL;
"""

MIGRATION = Migration(29, "build28_3_consolidated_device_registry", SQL)
