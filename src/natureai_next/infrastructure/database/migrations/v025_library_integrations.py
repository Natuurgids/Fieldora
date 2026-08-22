"""Fresh-schema Library media capabilities and integration control-plane foundation.

This migration creates the Release 3 structures only. It intentionally performs
no conversion or backfill of records from earlier Aperture schemas.
"""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE library_capabilities(
    capability_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN(0,1)),
    built_in INTEGER NOT NULL DEFAULT 1 CHECK(built_in IN(0,1)),
    display_order INTEGER NOT NULL,
    settings_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(settings_json)),
    updated_at_us INTEGER NOT NULL
);

INSERT INTO library_capabilities(capability_id,display_name,enabled,built_in,display_order,settings_json,updated_at_us) VALUES
('library.photos','Photographs',1,1,10,'{}',unixepoch('subsec')*1000000),
('library.sounds','Sounds',1,1,20,'{}',unixepoch('subsec')*1000000),
('library.videos','Videos',1,1,30,'{}',unixepoch('subsec')*1000000),
('library.documents','Documents',1,1,40,'{}',unixepoch('subsec')*1000000);

CREATE TABLE integration_systems(
    integration_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    version TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN(0,1)),
    availability_state TEXT NOT NULL DEFAULT 'available' CHECK(availability_state IN ('available','unavailable','unhealthy','not_installed')),
    database_relative_path TEXT,
    capability_manifest_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(capability_manifest_json)),
    settings_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(settings_json)),
    installed_at_us INTEGER,
    last_started_at_us INTEGER,
    last_stopped_at_us INTEGER,
    last_health_check_at_us INTEGER,
    last_error_code TEXT,
    last_error_summary TEXT
);

CREATE TABLE integration_capabilities(
    integration_id TEXT NOT NULL REFERENCES integration_systems(integration_id) ON DELETE CASCADE,
    capability_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN(0,1)),
    PRIMARY KEY(integration_id,capability_id)
);

INSERT INTO integration_systems(integration_id,display_name,provider_type,enabled,availability_state,database_relative_path,capability_manifest_json,installed_at_us)
VALUES
('aperture.enrichment','Aperture Enrichment Store','builtin',1,'available','subsystems/enrichment.sqlite3','["canonical-enrichment"]',unixepoch('subsec')*1000000),
('natureai.next','NatureAI Next','ai_engine',1,'available','subsystems/natureai.sqlite3','["image-analysis","embeddings","suggestions"]',unixepoch('subsec')*1000000),
('taxonomy.reference','Reference Taxonomy','taxonomy',1,'available','subsystems/taxonomy-reference.sqlite3','["taxonomy"]',unixepoch('subsec')*1000000),
('maps.offline','Offline Maps','map_provider',1,'available','subsystems/maps-offline.sqlite3','["offline-maps"]',unixepoch('subsec')*1000000),
('regional.knowledge','Regional Knowledge','enrichment',1,'available','subsystems/regional-knowledge.sqlite3','["regional-context"]',unixepoch('subsec')*1000000);

INSERT INTO integration_capabilities(integration_id,capability_id,enabled) VALUES
('aperture.enrichment','canonical-enrichment',1),
('natureai.next','image-analysis',1),
('natureai.next','embeddings',1),
('natureai.next','suggestions',1),
('taxonomy.reference','taxonomy',1),
('maps.offline','offline-maps',1),
('regional.knowledge','regional-context',1);

CREATE TABLE library_assets(
    asset_public_id TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL CHECK(asset_type IN ('photo','sound','video','document')),
    original_filename TEXT,
    primary_file_public_id TEXT,
    mime_type TEXT,
    file_extension TEXT,
    file_size_bytes INTEGER CHECK(file_size_bytes IS NULL OR file_size_bytes>=0),
    content_sha256 TEXT,
    title TEXT,
    description TEXT,
    availability_state TEXT NOT NULL DEFAULT 'available' CHECK(availability_state IN ('available','missing','offline','corrupt')),
    metadata_state TEXT NOT NULL DEFAULT 'pending' CHECK(metadata_state IN ('pending','ready','failed')),
    created_at_us INTEGER NOT NULL,
    updated_at_us INTEGER NOT NULL
);

CREATE TABLE photo_assets(
    asset_public_id TEXT PRIMARY KEY REFERENCES library_assets(asset_public_id) ON DELETE CASCADE,
    pixel_width INTEGER,
    pixel_height INTEGER,
    orientation INTEGER,
    bit_depth INTEGER,
    color_space TEXT,
    camera_make TEXT,
    camera_model TEXT,
    lens_model TEXT,
    capture_time_us INTEGER,
    capture_timezone TEXT,
    exposure_json TEXT
);

CREATE TABLE sound_assets(
    asset_public_id TEXT PRIMARY KEY REFERENCES library_assets(asset_public_id) ON DELETE CASCADE,
    duration_ms INTEGER,
    sample_rate_hz INTEGER,
    channel_count INTEGER,
    bit_depth INTEGER,
    codec TEXT,
    bitrate_bps INTEGER,
    recorded_at_us INTEGER,
    recording_timezone TEXT,
    recorder_make TEXT,
    recorder_model TEXT,
    microphone TEXT,
    latitude REAL,
    longitude REAL,
    altitude_metres REAL
);

CREATE TABLE video_assets(
    asset_public_id TEXT PRIMARY KEY REFERENCES library_assets(asset_public_id) ON DELETE CASCADE,
    duration_ms INTEGER,
    pixel_width INTEGER,
    pixel_height INTEGER,
    frame_rate REAL,
    video_codec TEXT,
    audio_codec TEXT,
    bitrate_bps INTEGER,
    recorded_at_us INTEGER,
    recording_timezone TEXT,
    camera_make TEXT,
    camera_model TEXT,
    latitude REAL,
    longitude REAL,
    altitude_metres REAL,
    rotation_degrees INTEGER
);

CREATE TABLE document_assets(
    asset_public_id TEXT PRIMARY KEY REFERENCES library_assets(asset_public_id) ON DELETE CASCADE,
    document_format TEXT,
    page_count INTEGER,
    author TEXT,
    subject TEXT,
    document_created_at_us INTEGER,
    document_modified_at_us INTEGER,
    language_code TEXT,
    searchable_text_available INTEGER NOT NULL DEFAULT 0 CHECK(searchable_text_available IN(0,1)),
    password_protected INTEGER NOT NULL DEFAULT 0 CHECK(password_protected IN(0,1))
);

CREATE INDEX idx_library_assets_type ON library_assets(asset_type,updated_at_us DESC);
CREATE INDEX idx_integration_systems_enabled ON integration_systems(enabled,provider_type);


"""

MIGRATION = Migration(25, "library media and integration architecture", SQL)
