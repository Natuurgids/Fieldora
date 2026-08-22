"""User-authored property enrichments and curated asset relationships."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
INSERT INTO enrichment_providers(
 provider_key,display_name,provider_version,runtime_status,source_status,
 storage_type,connection_reference,schema_version,installed_at_us,modified_at_us
) VALUES('aperture.user','User enrichments',NULL,'installed','not_required','sqlite','core://catalog',1,0,0);

INSERT INTO enrichment_provider_fields(
 provider_id,field_key,display_name,category,data_type,searchable,filterable,sortable,displayable,multi_value,
 supported_operators_json,configuration_json
)
SELECT id,'location.subject','Subject location','Geolocation','location',1,1,1,1,0,
 '["within","equals","is_empty","is_not_empty"]','{"historical":true,"capture_location_separate":true}'
FROM enrichment_providers WHERE provider_key='aperture.user';

CREATE TABLE asset_relationship_groups(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 relationship_type TEXT NOT NULL CHECK(relationship_type IN(
  'exact_duplicate','visual_duplicate','near_duplicate','derived_version','edited_version',
  'alternate_format','burst_related','same_observation','panorama_member','focus_stack'
 )),
 title TEXT,
 current_asset_id INTEGER REFERENCES assets(id) ON DELETE RESTRICT,
 lifecycle_status TEXT NOT NULL DEFAULT 'active' CHECK(lifecycle_status IN('active','reversed','superseded','withdrawn')),
 provider_key TEXT NOT NULL,
 confidence REAL,
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL
);

CREATE TABLE asset_relationship_members(
 group_id INTEGER NOT NULL REFERENCES asset_relationship_groups(id) ON DELETE RESTRICT,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
 member_role TEXT NOT NULL DEFAULT 'related' CHECK(member_role IN('current','duplicate','derived','related')),
 source_location TEXT,
 created_at_us INTEGER NOT NULL,
 PRIMARY KEY(group_id,asset_id)
);
CREATE INDEX ix_asset_relationship_members_asset ON asset_relationship_members(asset_id,group_id);

CREATE TABLE asset_relationship_decisions(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 group_id INTEGER NOT NULL REFERENCES asset_relationship_groups(id) ON DELETE RESTRICT,
 action TEXT NOT NULL CHECK(action IN('created','confirmed','set_current','retitled','reversed','superseded')),
 previous_value_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(previous_value_json)),
 new_value_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(new_value_json)),
 actor TEXT NOT NULL DEFAULT 'local_user',
 created_at_us INTEGER NOT NULL
);
"""

MIGRATION = Migration(24, "user_and_relationship_enrichments", SQL)
