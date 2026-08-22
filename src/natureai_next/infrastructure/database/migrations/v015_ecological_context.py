"""Local conservation, seasonality, migration, and habitat context."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE ecological_context(
 taxon_id INTEGER PRIMARY KEY REFERENCES taxa(id) ON DELETE CASCADE,
 conservation_status TEXT,
 seasonal_months TEXT,
 migration_status TEXT,
 habitats TEXT,
 source_name TEXT NOT NULL,
 source_version TEXT,
 source_url TEXT,
 updated_at_us INTEGER NOT NULL
);
CREATE INDEX ix_ecological_context_status ON ecological_context(conservation_status,taxon_id);
"""
MIGRATION = Migration(15, "ecological_context", SQL)
