"""Temporal map and movement semantics for longitudinal observations."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE observation_series ADD COLUMN subject_type TEXT NOT NULL DEFAULT 'unspecified'
 CHECK(subject_type IN ('unspecified','individual_organism','tagged_animal','population','flock','herd','colony','migration_study','monitoring_site','habitat','plant_specimen','vegetation_plot'));
ALTER TABLE observation_series ADD COLUMN subject_identifier TEXT;
ALTER TABLE observation_series ADD COLUMN identity_confidence TEXT NOT NULL DEFAULT 'unknown'
 CHECK(identity_confidence IN ('confirmed','probable','inferred','unknown'));
ALTER TABLE observation_series ADD COLUMN tracking_method TEXT NOT NULL DEFAULT 'observation'
 CHECK(tracking_method IN ('observation','visual_identity','tag','gps_device','radio_telemetry','camera_trap','user_linked','other'));
ALTER TABLE observation_series ADD COLUMN connection_policy TEXT NOT NULL DEFAULT 'observed_locations'
 CHECK(connection_policy IN ('observed_locations','inferred_distribution','confirmed_movement'));

ALTER TABLE observation_series_members ADD COLUMN identity_confidence TEXT NOT NULL DEFAULT 'unknown'
 CHECK(identity_confidence IN ('confirmed','probable','inferred','unknown'));
ALTER TABLE observation_series_members ADD COLUMN verified INTEGER NOT NULL DEFAULT 0 CHECK(verified IN (0,1));
ALTER TABLE observation_series_members ADD COLUMN tracking_timestamp_us INTEGER;
ALTER TABLE observation_series_members ADD COLUMN notes TEXT;
CREATE INDEX ix_observation_series_members_time ON observation_series_members(series_id,tracking_timestamp_us,sequence_number,observation_id);

CREATE TABLE movement_segments(
 id INTEGER PRIMARY KEY,
 public_id TEXT NOT NULL UNIQUE,
 series_id INTEGER NOT NULL REFERENCES observation_series(id) ON DELETE CASCADE,
 origin_observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 destination_observation_id INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
 movement_classification TEXT NOT NULL DEFAULT 'movement'
   CHECK(movement_classification IN ('movement','migration','dispersal','local_range','return','unknown')),
 confidence TEXT NOT NULL DEFAULT 'unknown' CHECK(confidence IN ('confirmed','probable','inferred','unknown')),
 verified INTEGER NOT NULL DEFAULT 0 CHECK(verified IN (0,1)),
 distance_m REAL CHECK(distance_m IS NULL OR distance_m>=0),
 duration_us INTEGER CHECK(duration_us IS NULL OR duration_us>=0),
 notes TEXT,
 created_at_us INTEGER NOT NULL,
 modified_at_us INTEGER NOT NULL,
 UNIQUE(series_id,origin_observation_id,destination_observation_id),
 CHECK(origin_observation_id<>destination_observation_id)
);
CREATE INDEX ix_movement_segments_series ON movement_segments(series_id,origin_observation_id,destination_observation_id);
"""

MIGRATION = Migration(19, "temporal_movement", SQL)
