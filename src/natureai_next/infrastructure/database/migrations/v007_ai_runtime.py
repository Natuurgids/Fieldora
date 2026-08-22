"""Production AI runtime, inference-run, and index-audit persistence."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE inference_runs ADD COLUMN precision TEXT NOT NULL DEFAULT 'fp32';
ALTER TABLE inference_runs ADD COLUMN requested_item_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE inference_runs ADD COLUMN completed_item_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE inference_runs ADD COLUMN failed_item_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE inference_runs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE inference_runs ADD COLUMN final_batch_size INTEGER;
ALTER TABLE inference_runs ADD COLUMN error_text TEXT;
CREATE INDEX ix_inference_runs_outcome_created ON inference_runs(outcome,started_at_us,id);
CREATE INDEX ix_inference_runs_job ON inference_runs(job_id);
ALTER TABLE vector_index_generations ADD COLUMN validation_error TEXT;
ALTER TABLE vector_index_generations ADD COLUMN validated_at_us INTEGER;
ALTER TABLE vector_index_generations ADD COLUMN backend TEXT NOT NULL DEFAULT 'local_exact';
CREATE INDEX ix_vector_index_state ON vector_index_generations(state,model_variant_id,preprocessing_identity);
CREATE TABLE ai_runtime_state(
 id INTEGER PRIMARY KEY CHECK(id=1),
 active_provider TEXT,
 active_device TEXT,
 active_precision TEXT,
 last_diagnostics_json TEXT CHECK(last_diagnostics_json IS NULL OR json_valid(last_diagnostics_json)),
 last_diagnostics_at_us INTEGER,
 modified_at_us INTEGER NOT NULL
);
CREATE TABLE embedding_audit_runs(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 model_variant_id INTEGER NOT NULL REFERENCES model_variants(id) ON DELETE CASCADE,
 preprocessing_identity TEXT NOT NULL,
 checked_count INTEGER NOT NULL DEFAULT 0,
 corrupt_count INTEGER NOT NULL DEFAULT 0,
 stale_count INTEGER NOT NULL DEFAULT 0,
 repaired_count INTEGER NOT NULL DEFAULT 0,
 started_at_us INTEGER NOT NULL,
 completed_at_us INTEGER,
 result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json))
);
"""
MIGRATION = Migration(7, "ai_production_runtime", SQL)
