"""Authoritative taxonomy package provenance and AI label mappings."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    3,
    "authoritative_taxonomy_packages",
    """
ALTER TABLE taxonomy_datasets ADD COLUMN license_url TEXT;
ALTER TABLE taxonomy_datasets ADD COLUMN redistribution_allowed INTEGER NOT NULL DEFAULT 0 CHECK(redistribution_allowed IN (0,1));
ALTER TABLE taxonomy_datasets ADD COLUMN source_url TEXT;
ALTER TABLE taxonomy_datasets ADD COLUMN package_schema_version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE reference_taxon_names ADD COLUMN source_record_id TEXT;
ALTER TABLE reference_taxon_names ADD COLUMN verification_state TEXT NOT NULL DEFAULT 'source' CHECK(verification_state IN ('source','verified','user','unverified'));

CREATE TABLE ai_taxon_label_mappings (
    id INTEGER PRIMARY KEY,
    model_family TEXT NOT NULL,
    model_version TEXT NOT NULL,
    label TEXT NOT NULL,
    reference_taxon_public_id TEXT NOT NULL,
    mapping_state TEXT NOT NULL DEFAULT 'confirmed' CHECK(mapping_state IN ('confirmed','probable','rejected')),
    source TEXT NOT NULL,
    mapped_at_us INTEGER NOT NULL,
    notes TEXT,
    UNIQUE(model_family, model_version, label)
);
CREATE INDEX ix_ai_taxon_label_reference
    ON ai_taxon_label_mappings(reference_taxon_public_id, model_family, model_version);
""",
)
