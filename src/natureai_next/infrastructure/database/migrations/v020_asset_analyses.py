"""Immutable, versioned asset analysis and enrichment records."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE asset_analyses(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 engine_id TEXT NOT NULL,
 engine_family TEXT NOT NULL,
 model_name TEXT,
 model_version TEXT,
 analysis_kind TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN('running','succeeded','completed_with_errors','failed','cancelled')),
 configuration_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(configuration_json)),
 configuration_hash TEXT NOT NULL CHECK(length(configuration_hash)=64),
 result_summary_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result_summary_json)),
 source_sha256 TEXT,
 application_version TEXT NOT NULL,
 started_at_us INTEGER NOT NULL,
 completed_at_us INTEGER,
 created_at_us INTEGER NOT NULL,
 supersedes_analysis_id INTEGER REFERENCES asset_analyses(id),
 CHECK(completed_at_us IS NULL OR completed_at_us>=started_at_us)
);
CREATE INDEX ix_asset_analyses_asset ON asset_analyses(asset_id,created_at_us DESC,id DESC);
CREATE INDEX ix_asset_analyses_engine ON asset_analyses(engine_id,model_version,status,created_at_us DESC);

CREATE TABLE analysis_taxon_candidates(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 analysis_id INTEGER NOT NULL REFERENCES asset_analyses(id) ON DELETE CASCADE,
 local_taxon_id INTEGER REFERENCES taxa(id),
 reference_taxon_public_id TEXT,
 model_label TEXT NOT NULL,
 rank INTEGER NOT NULL CHECK(rank>0),
 raw_score REAL NOT NULL,
 calibrated_score REAL,
 confidence_band TEXT NOT NULL DEFAULT 'unclassified' CHECK(confidence_band IN('high','medium','low','unknown','unclassified')),
 taxonomic_level TEXT,
 provenance_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(provenance_json)),
 created_at_us INTEGER NOT NULL,
 UNIQUE(analysis_id,rank)
);
CREATE INDEX ix_analysis_taxon_candidates_analysis ON analysis_taxon_candidates(analysis_id,rank);
CREATE INDEX ix_analysis_taxon_candidates_reference ON analysis_taxon_candidates(reference_taxon_public_id,analysis_id);

CREATE TABLE analysis_tags(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 analysis_id INTEGER NOT NULL REFERENCES asset_analyses(id) ON DELETE CASCADE,
 namespace TEXT NOT NULL DEFAULT 'general',
 tag TEXT NOT NULL,
 confidence REAL,
 provenance_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(provenance_json)),
 created_at_us INTEGER NOT NULL,
 UNIQUE(analysis_id,namespace,tag)
);
CREATE INDEX ix_analysis_tags_analysis ON analysis_tags(analysis_id,namespace,tag);

CREATE TABLE analysis_observation_promotions(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 analysis_id INTEGER NOT NULL REFERENCES asset_analyses(id) ON DELETE RESTRICT,
 candidate_id INTEGER REFERENCES analysis_taxon_candidates(id) ON DELETE SET NULL,
 observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE RESTRICT,
 promotion_state TEXT NOT NULL CHECK(promotion_state IN('accepted','rejected','superseded')),
 actor TEXT NOT NULL DEFAULT 'local_user',
 reason TEXT,
 created_at_us INTEGER NOT NULL
);
CREATE INDEX ix_analysis_promotions_analysis ON analysis_observation_promotions(analysis_id,created_at_us,id);
CREATE INDEX ix_analysis_promotions_observation ON analysis_observation_promotions(observation_id,created_at_us,id);

ALTER TABLE ai_suggestions ADD COLUMN analysis_id INTEGER REFERENCES asset_analyses(id) ON DELETE SET NULL;
CREATE INDEX ix_ai_suggestions_analysis ON ai_suggestions(analysis_id,rank,id);
"""

MIGRATION = Migration(20, "asset_analyses", SQL)
