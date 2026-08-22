"""Provider-independent enrichment registry and append-only enrichment history."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE enrichment_providers(
 id INTEGER PRIMARY KEY,
 provider_key TEXT NOT NULL UNIQUE,
 display_name TEXT NOT NULL,
 provider_version TEXT,
 runtime_status TEXT NOT NULL DEFAULT 'installed'
  CHECK(runtime_status IN('installed','disabled','removed')),
 source_status TEXT NOT NULL DEFAULT 'available'
  CHECK(source_status IN('available','detached','removed','not_required')),
 storage_type TEXT NOT NULL DEFAULT 'sqlite',
 connection_reference TEXT,
 schema_version INTEGER,
 installed_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL,
 removed_at_us INTEGER
);

CREATE TABLE enrichment_provider_fields(
 id INTEGER PRIMARY KEY,
 provider_id INTEGER NOT NULL REFERENCES enrichment_providers(id),
 field_key TEXT NOT NULL,
 display_name TEXT NOT NULL,
 category TEXT NOT NULL,
 data_type TEXT NOT NULL,
 searchable INTEGER NOT NULL DEFAULT 1 CHECK(searchable IN(0,1)),
 filterable INTEGER NOT NULL DEFAULT 1 CHECK(filterable IN(0,1)),
 sortable INTEGER NOT NULL DEFAULT 0 CHECK(sortable IN(0,1)),
 displayable INTEGER NOT NULL DEFAULT 1 CHECK(displayable IN(0,1)),
 multi_value INTEGER NOT NULL DEFAULT 0 CHECK(multi_value IN(0,1)),
 supported_operators_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(supported_operators_json)),
 configuration_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(configuration_json)),
 UNIQUE(provider_id,field_key)
);

CREATE TABLE canonical_enrichments(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
 provider_id INTEGER NOT NULL REFERENCES enrichment_providers(id),
 field_id INTEGER NOT NULL REFERENCES enrichment_provider_fields(id),
 source_suggestion_id INTEGER REFERENCES ai_suggestions(id) ON DELETE SET NULL,
 source_review_action_id INTEGER REFERENCES ai_review_actions(id) ON DELETE SET NULL,
 source_observation_id INTEGER REFERENCES observations(id) ON DELETE SET NULL,
 source_record_reference TEXT,
 value_type TEXT NOT NULL,
 display_value TEXT,
 normalized_value TEXT,
 value_json TEXT NOT NULL CHECK(json_valid(value_json)),
 confidence REAL,
 provenance_json TEXT NOT NULL CHECK(json_valid(provenance_json)),
 lifecycle_status TEXT NOT NULL DEFAULT 'active'
  CHECK(lifecycle_status IN('active','reversed','superseded','withdrawn')),
 valid_from_us INTEGER NOT NULL,
 valid_to_us INTEGER,
 accepted_at_us INTEGER NOT NULL,
 accepted_by TEXT NOT NULL DEFAULT 'local_user',
 reversed_at_us INTEGER,
 reversed_by TEXT,
 reversal_reason TEXT,
 supersedes_enrichment_id INTEGER REFERENCES canonical_enrichments(id),
 superseded_by_enrichment_id INTEGER REFERENCES canonical_enrichments(id),
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL
);
CREATE INDEX ix_canonical_enrichments_asset_status
 ON canonical_enrichments(asset_id,lifecycle_status,field_id,id);
CREATE INDEX ix_canonical_enrichments_search_text
 ON canonical_enrichments(field_id,normalized_value,lifecycle_status);
CREATE INDEX ix_canonical_enrichments_provider
 ON canonical_enrichments(provider_id,lifecycle_status,id);

CREATE TABLE enrichment_purge_audit(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 scope_json TEXT NOT NULL CHECK(json_valid(scope_json)),
 affected_record_count INTEGER NOT NULL CHECK(affected_record_count>=0),
 reason TEXT NOT NULL,
 actor TEXT NOT NULL,
 created_at_us INTEGER NOT NULL
);

INSERT INTO enrichment_providers(
 provider_key,display_name,provider_version,runtime_status,source_status,
 storage_type,connection_reference,schema_version,installed_at_us,modified_at_us
) VALUES(
 'aperture.bioclip','BioCLIP Taxonomy',NULL,'installed','available',
 'sqlite','core://ai-review',1,0,0
);

INSERT INTO enrichment_provider_fields(
 provider_id,field_key,display_name,category,data_type,searchable,filterable,
 sortable,displayable,multi_value,supported_operators_json,configuration_json
)
SELECT id,'taxonomy.accepted','Accepted taxonomy','AI enrichment','taxonomy',
 1,1,1,1,1,
 '["equals","is_descendant_of","is_empty","is_not_empty"]',
 '{"canonical":true}'
FROM enrichment_providers WHERE provider_key='aperture.bioclip';
"""

MIGRATION = Migration(23, "canonical_enrichment_history", SQL)
