"""Indexes supporting hierarchical located-media map aggregation."""
from natureai_next.infrastructure.database.migrations.core import Migration
SQL = r"""
CREATE INDEX IF NOT EXISTS ix_asset_locations_location_role_asset ON asset_locations(location_id,role,asset_id);
CREATE INDEX IF NOT EXISTS ix_assets_lifecycle_media ON assets(lifecycle_state,media_type,id);
CREATE INDEX IF NOT EXISTS ix_locations_admin_hierarchy ON locations(country_code,admin_area_1,admin_area_2,locality);
"""
MIGRATION = Migration(26, "spatial_asset_hierarchy", SQL)
