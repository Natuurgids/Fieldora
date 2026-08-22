"""Build 28.2 persistent device identity for linked originals."""
from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE asset_storage_locations ADD COLUMN device_identity TEXT;
ALTER TABLE asset_storage_locations ADD COLUMN volume_label TEXT;
ALTER TABLE asset_storage_locations ADD COLUMN relative_path TEXT;
ALTER TABLE asset_storage_locations ADD COLUMN last_mount_path TEXT;

CREATE INDEX ix_asset_storage_locations_device
ON asset_storage_locations(device_identity,health,asset_id)
WHERE device_identity IS NOT NULL;
"""

MIGRATION = Migration(28, "build28_2_storage_device_identity", SQL)
