"""Links library assets to independently owned external taxonomy sources."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE asset_taxonomy_enrichments(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 source_key TEXT NOT NULL,
 source_taxon_id TEXT NOT NULL,
 scientific_name TEXT NOT NULL,
 vernacular_name TEXT,
 rank TEXT,
 source_database_identity TEXT NOT NULL,
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL,
 UNIQUE(asset_id, source_key)
);
CREATE INDEX ix_asset_taxonomy_enrichment_name ON asset_taxonomy_enrichments(scientific_name COLLATE NOCASE);
CREATE INDEX ix_asset_taxonomy_enrichment_source_taxon ON asset_taxonomy_enrichments(source_key,source_taxon_id);
"""
MIGRATION = Migration(22, "external_taxonomy_enrichment", SQL)
