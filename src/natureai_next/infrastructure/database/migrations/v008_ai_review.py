"""AI prompt sets, suggestion provenance, and append-only review actions."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE prompt_sets(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 identity TEXT NOT NULL,
 semantic_version TEXT NOT NULL,
 model_family TEXT NOT NULL,
 checksum TEXT NOT NULL CHECK(length(checksum)=64),
 manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
 active INTEGER NOT NULL DEFAULT 0 CHECK(active IN(0,1)),
 installed_at_us INTEGER NOT NULL,
 UNIQUE(identity,semantic_version)
);
CREATE UNIQUE INDEX ux_prompt_sets_active ON prompt_sets(identity) WHERE active=1;
ALTER TABLE ai_suggestions RENAME TO ai_suggestions_v1;
CREATE TABLE ai_suggestions(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
 observation_id INTEGER REFERENCES observations(id) ON DELETE SET NULL,
 region_of_interest_id INTEGER REFERENCES regions_of_interest(id) ON DELETE SET NULL,
 inference_run_id INTEGER NOT NULL REFERENCES inference_runs(id),
 prompt_set_id INTEGER REFERENCES prompt_sets(id),
 suggestion_type TEXT NOT NULL,
 candidate_taxon_id INTEGER REFERENCES taxa(id),
 candidate_label TEXT,
 raw_score REAL NOT NULL,
 rank INTEGER NOT NULL CHECK(rank>0),
 calibrated_score REAL,
 calibration_identity TEXT,
 score_type TEXT NOT NULL DEFAULT 'cosine',
 confidence_band TEXT NOT NULL DEFAULT 'unclassified' CHECK(confidence_band IN('high','medium','low','unknown','unclassified')),
 taxonomic_level TEXT,
 geographic_context_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(geographic_context_json)),
 provenance_json TEXT NOT NULL CHECK(json_valid(provenance_json)),
 review_state TEXT NOT NULL CHECK(review_state IN('pending','accepted','rejected','deferred','superseded')),
 reviewed_at_us INTEGER,
 user_action_public_id TEXT,
 supersedes_suggestion_id INTEGER REFERENCES ai_suggestions(id),
 created_at_us INTEGER NOT NULL DEFAULT 0,
 CHECK(asset_id IS NOT NULL OR observation_id IS NOT NULL)
);
INSERT INTO ai_suggestions(id,public_id,asset_id,observation_id,inference_run_id,suggestion_type,candidate_taxon_id,candidate_label,raw_score,rank,calibrated_score,calibration_identity,provenance_json,review_state,reviewed_at_us,user_action_public_id,created_at_us)
SELECT id,public_id,asset_id,observation_id,inference_run_id,suggestion_type,candidate_taxon_id,candidate_label,raw_score,rank,calibrated_score,calibration_identity,provenance_json,review_state,reviewed_at_us,user_action_public_id,0 FROM ai_suggestions_v1;
DROP TABLE ai_suggestions_v1;
CREATE INDEX ix_ai_suggestions_review ON ai_suggestions(review_state,confidence_band,id);
CREATE INDEX ix_ai_suggestions_asset ON ai_suggestions(asset_id,review_state,id);
CREATE INDEX ix_ai_suggestions_taxon ON ai_suggestions(candidate_taxon_id,review_state);
CREATE TABLE ai_review_actions(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 suggestion_id INTEGER NOT NULL REFERENCES ai_suggestions(id) ON DELETE CASCADE,
 action TEXT NOT NULL CHECK(action IN('accept','reject','defer','supersede','reverse_accept')),
 prior_state TEXT NOT NULL,
 resulting_state TEXT NOT NULL,
 created_observation_id INTEGER REFERENCES observations(id) ON DELETE SET NULL,
 created_observation_revision INTEGER,
 reason TEXT,
 actor TEXT NOT NULL DEFAULT 'local_user',
 created_at_us INTEGER NOT NULL
);
CREATE INDEX ix_ai_review_actions_suggestion ON ai_review_actions(suggestion_id,id);
CREATE TABLE ai_review_sessions(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 state_json TEXT NOT NULL CHECK(json_valid(state_json)),
 modified_at_us INTEGER NOT NULL
);
"""
MIGRATION = Migration(8, "ai_suggestions_review", SQL)
