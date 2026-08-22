"""Taxonomy text embeddings, AI review sessions, and duplicate groups."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE taxonomy_text_embeddings(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 taxon_id INTEGER REFERENCES taxa(id) ON DELETE CASCADE,
 broad_group TEXT,
 label_kind TEXT NOT NULL CHECK(label_kind IN('scientific','vernacular','synonym','broad_group')),
 language_tag TEXT,
 region_code TEXT,
 source_text TEXT NOT NULL,
 source_text_sha256 TEXT NOT NULL CHECK(length(source_text_sha256)=64),
 model_variant_id INTEGER NOT NULL REFERENCES model_variants(id),
 preprocessing_identity TEXT NOT NULL,
 prompt_set_id INTEGER REFERENCES prompt_sets(id) ON DELETE SET NULL,
 dimension INTEGER NOT NULL CHECK(dimension>0),
 vector_blob BLOB NOT NULL,
 vector_sha256 TEXT NOT NULL CHECK(length(vector_sha256)=64),
 valid INTEGER NOT NULL DEFAULT 1 CHECK(valid IN(0,1)),
 created_at_us INTEGER NOT NULL,
 CHECK((taxon_id IS NOT NULL) <> (broad_group IS NOT NULL))
);
CREATE UNIQUE INDEX ux_taxonomy_text_embedding_identity ON taxonomy_text_embeddings(
 COALESCE(taxon_id,-1),COALESCE(broad_group,''),label_kind,COALESCE(language_tag,''),
 COALESCE(region_code,''),model_variant_id,preprocessing_identity,COALESCE(prompt_set_id,-1)
) WHERE valid=1;
CREATE INDEX ix_taxonomy_text_embeddings_lookup ON taxonomy_text_embeddings(model_variant_id,preprocessing_identity,valid,id);

CREATE TABLE near_duplicate_groups(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 model_variant_id INTEGER NOT NULL REFERENCES model_variants(id),
 preprocessing_identity TEXT NOT NULL,
 threshold REAL NOT NULL CHECK(threshold>=-1.0 AND threshold<=1.0),
 created_at_us INTEGER NOT NULL
);
CREATE TABLE near_duplicate_group_members(
 group_id INTEGER NOT NULL REFERENCES near_duplicate_groups(id) ON DELETE CASCADE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 similarity REAL NOT NULL CHECK(similarity>=-1.0 AND similarity<=1.0),
 position INTEGER NOT NULL CHECK(position>=0),
 PRIMARY KEY(group_id,asset_id),
 UNIQUE(group_id,position)
);
CREATE INDEX ix_near_duplicate_members_asset ON near_duplicate_group_members(asset_id,group_id);

CREATE UNIQUE INDEX ux_ai_review_sessions_singleton ON ai_review_sessions((1));
"""
MIGRATION = Migration(9, "ai_generation_review_state", SQL)
