"""Stable links between library taxa and shared reference taxa."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    2,
    "library_taxon_reference_links",
    """
CREATE TABLE library_taxon_links (
    id INTEGER PRIMARY KEY,
    library_public_id TEXT NOT NULL,
    local_taxon_public_id TEXT NOT NULL,
    reference_taxon_public_id TEXT NOT NULL,
    link_state TEXT NOT NULL DEFAULT 'confirmed' CHECK(link_state IN ('confirmed','probable','rejected')),
    source TEXT NOT NULL,
    linked_at_us INTEGER NOT NULL,
    notes TEXT,
    UNIQUE(library_public_id, local_taxon_public_id)
);
CREATE INDEX ix_library_taxon_links_reference
    ON library_taxon_links(reference_taxon_public_id, library_public_id);
""",
)
