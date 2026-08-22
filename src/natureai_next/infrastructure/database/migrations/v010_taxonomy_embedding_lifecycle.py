"""Taxonomy embedding generation provenance and lifecycle indexes."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE taxonomy_text_embeddings ADD COLUMN generation_identity TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE taxonomy_text_embeddings ADD COLUMN taxonomy_source_ids_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(taxonomy_source_ids_json));
CREATE INDEX ix_taxonomy_text_embeddings_generation ON taxonomy_text_embeddings(generation_identity,valid,id);
"""

MIGRATION = Migration(10, "taxonomy_embedding_lifecycle", SQL)
