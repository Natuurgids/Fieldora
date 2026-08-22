"""Taxonomy display preferences and package lifecycle metadata."""

from natureai_next.infrastructure.database.migrations.core import Migration

MIGRATION = Migration(
    4,
    "taxonomy_preferences",
    """
CREATE TABLE taxonomy_preferences (
    id INTEGER PRIMARY KEY CHECK(id=1),
    language_tag TEXT,
    region_code TEXT,
    prefer_common_name INTEGER NOT NULL DEFAULT 1 CHECK(prefer_common_name IN (0,1)),
    updated_at_us INTEGER NOT NULL
);
INSERT INTO taxonomy_preferences(id,language_tag,region_code,prefer_common_name,updated_at_us)
VALUES(1,NULL,NULL,1,0);

ALTER TABLE taxonomy_datasets ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1));
ALTER TABLE taxonomy_datasets ADD COLUMN disabled_at_us INTEGER;
CREATE INDEX ix_taxonomy_datasets_enabled ON taxonomy_datasets(enabled,active,source_name);
""",
)
