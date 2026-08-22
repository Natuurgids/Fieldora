"""Taxonomy package metadata, observation history, and searchable names."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE taxonomy_sources ADD COLUMN package_id TEXT;
ALTER TABLE taxonomy_sources ADD COLUMN attribution_text TEXT NOT NULL DEFAULT '';
ALTER TABLE taxonomy_sources ADD COLUMN manifest_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(manifest_json));
ALTER TABLE taxonomy_sources ADD COLUMN signature_key_id TEXT;
CREATE UNIQUE INDEX ux_taxonomy_sources_package_id ON taxonomy_sources(package_id) WHERE package_id IS NOT NULL;
CREATE INDEX ix_taxon_names_lookup ON taxon_names(name COLLATE NOCASE,language_tag,region_code,preferred);
CREATE INDEX ix_taxon_regions_region ON taxon_regions(region_code,occurrence_status,taxon_id);
CREATE TABLE observation_revisions(id INTEGER PRIMARY KEY,observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,revision INTEGER NOT NULL,snapshot_json TEXT NOT NULL CHECK(json_valid(snapshot_json)),changed_at_us INTEGER NOT NULL,UNIQUE(observation_id,revision));
CREATE INDEX ix_observation_revisions_observation ON observation_revisions(observation_id,revision);
CREATE TABLE taxonomy_preferences(id INTEGER PRIMARY KEY CHECK(id=1),preferred_language_tag TEXT,preferred_region_code TEXT,modified_at_us INTEGER NOT NULL);
"""
MIGRATION = Migration(5, "taxonomy_system", SQL)
