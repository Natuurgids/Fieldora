"""AI model registry, embedding provenance, and vector-index generations."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE model_packages ADD COLUMN package_id TEXT;
ALTER TABLE model_packages ADD COLUMN signature_key_id TEXT;
ALTER TABLE model_packages ADD COLUMN activated_at_us INTEGER;
ALTER TABLE model_packages ADD COLUMN active INTEGER NOT NULL DEFAULT 0 CHECK(active IN(0,1));
CREATE UNIQUE INDEX ux_model_packages_package_id ON model_packages(package_id) WHERE package_id IS NOT NULL;
ALTER TABLE model_variants ADD COLUMN input_size INTEGER;
ALTER TABLE model_variants ADD COLUMN normalized_output INTEGER NOT NULL DEFAULT 1 CHECK(normalized_output IN(0,1));
ALTER TABLE model_variants ADD COLUMN artifact_relative_path TEXT;
ALTER TABLE embeddings ADD COLUMN source_sha256 TEXT;
ALTER TABLE embeddings ADD COLUMN execution_provider TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE embeddings ADD COLUMN precision TEXT NOT NULL DEFAULT 'fp32';
ALTER TABLE embeddings ADD COLUMN application_version TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE embeddings ADD COLUMN inference_run_id INTEGER REFERENCES inference_runs(id);
ALTER TABLE embeddings ADD COLUMN validity_state TEXT NOT NULL DEFAULT 'valid' CHECK(validity_state IN('valid','stale','corrupt'));
CREATE INDEX ix_embeddings_valid_model ON embeddings(model_variant_id,preprocessing_identity,validity_state,asset_id);
CREATE TABLE vector_index_generations(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 model_variant_id INTEGER NOT NULL REFERENCES model_variants(id) ON DELETE CASCADE,
 preprocessing_identity TEXT NOT NULL,
 metric TEXT NOT NULL CHECK(metric IN('cosine')),
 generation TEXT NOT NULL,
 index_path_token TEXT NOT NULL,
 manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
 index_checksum TEXT NOT NULL,
 source_row_count INTEGER NOT NULL CHECK(source_row_count>=0),
 state TEXT NOT NULL CHECK(state IN('building','active','corrupt','superseded')),
 created_at_us INTEGER NOT NULL,
 activated_at_us INTEGER,
 UNIQUE(model_variant_id,preprocessing_identity,generation)
);
CREATE UNIQUE INDEX ux_vector_index_active ON vector_index_generations(model_variant_id,preprocessing_identity) WHERE state='active';
"""
MIGRATION = Migration(6, "ai_foundation", SQL)
