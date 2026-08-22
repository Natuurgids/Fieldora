"""Initial shared taxonomy-reference and knowledge metadata schema."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    1,
    "taxonomy_reference_catalog",
    """
CREATE TABLE taxonomy_datasets (
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    source_version TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    license_name TEXT NOT NULL,
    attribution TEXT NOT NULL,
    installed_at_us INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    UNIQUE(source_name, source_version)
);
CREATE TABLE reference_taxa (
    id INTEGER PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES taxonomy_datasets(id) ON DELETE CASCADE,
    public_id TEXT NOT NULL UNIQUE,
    source_taxon_id TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    authorship TEXT,
    rank TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('accepted','synonym','unresolved')),
    parent_public_id TEXT,
    accepted_public_id TEXT,
    kingdom TEXT,
    major_group TEXT,
    extinct INTEGER NOT NULL DEFAULT 0 CHECK(extinct IN (0,1)),
    UNIQUE(dataset_id, source_taxon_id)
);
CREATE INDEX ix_reference_taxa_name ON reference_taxa(scientific_name COLLATE NOCASE);
CREATE INDEX ix_reference_taxa_parent ON reference_taxa(parent_public_id, scientific_name);
CREATE TABLE reference_taxon_names (
    id INTEGER PRIMARY KEY,
    taxon_public_id TEXT NOT NULL,
    name TEXT NOT NULL,
    name_type TEXT NOT NULL,
    language_tag TEXT,
    region_code TEXT,
    preferred INTEGER NOT NULL DEFAULT 0 CHECK(preferred IN (0,1)),
    source TEXT NOT NULL,
    UNIQUE(taxon_public_id, name, name_type, language_tag, region_code, source)
);
CREATE INDEX ix_reference_taxon_names_lookup ON reference_taxon_names(name COLLATE NOCASE, language_tag, region_code);
CREATE TABLE reference_taxon_facts (
    id INTEGER PRIMARY KEY,
    taxon_public_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    value_text TEXT NOT NULL,
    language_tag TEXT,
    region_code TEXT,
    source TEXT NOT NULL,
    source_url TEXT,
    observed_at_us INTEGER,
    UNIQUE(taxon_public_id, fact_type, value_text, language_tag, region_code, source)
);
CREATE INDEX ix_reference_taxon_facts_taxon ON reference_taxon_facts(taxon_public_id, fact_type);
CREATE TABLE reference_taxon_distributions (
    id INTEGER PRIMARY KEY,
    taxon_public_id TEXT NOT NULL,
    region_code TEXT NOT NULL,
    occurrence_status TEXT,
    establishment_means TEXT,
    source TEXT NOT NULL,
    UNIQUE(taxon_public_id, region_code, source)
);
CREATE INDEX ix_reference_taxon_distribution_region ON reference_taxon_distributions(region_code, occurrence_status);
CREATE TABLE reference_taxon_links (
    id INTEGER PRIMARY KEY,
    taxon_public_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    url TEXT,
    source TEXT NOT NULL,
    UNIQUE(taxon_public_id, relation_type, title, source)
);
""",
)
