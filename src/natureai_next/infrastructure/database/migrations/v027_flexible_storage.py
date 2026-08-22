"""Build 28 canonical flexible-storage schema."""
from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
CREATE TABLE storage_providers(
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK(kind IN ('aperture_library','local_filesystem','removable_volume','network_share','cloud_sync','camera_device','unknown')),
    display_name TEXT NOT NULL,
    root_uri TEXT,
    volume_identity TEXT,
    configuration_json TEXT NOT NULL DEFAULT '{}',
    created_at_us INTEGER NOT NULL,
    modified_at_us INTEGER NOT NULL
);

CREATE TABLE asset_storage_policies(
    asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
    policy TEXT NOT NULL CHECK(policy IN ('managed','referenced','hybrid')),
    created_at_us INTEGER NOT NULL,
    modified_at_us INTEGER NOT NULL
);

CREATE TABLE asset_storage_locations(
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES storage_providers(id),
    file_instance_id INTEGER REFERENCES file_instances(id) ON DELETE SET NULL,
    role TEXT NOT NULL CHECK(role IN ('source','aperture_master')),
    normalized_path TEXT NOT NULL,
    path_key TEXT NOT NULL,
    source_uri TEXT,
    file_size INTEGER CHECK(file_size IS NULL OR file_size >= 0),
    modified_at_observed_us INTEGER,
    sha256 TEXT CHECK(sha256 IS NULL OR (length(sha256)=64 AND sha256=lower(sha256))),
    fast_fingerprint TEXT,
    health TEXT NOT NULL CHECK(health IN ('available','offline','missing','changed','corrupt','permission_denied','cloud_placeholder','unverified')),
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK(is_primary IN (0,1)),
    last_verified_at_us INTEGER,
    created_at_us INTEGER NOT NULL,
    modified_at_us INTEGER NOT NULL,
    UNIQUE(asset_id,role,path_key)
);
CREATE INDEX ix_asset_storage_locations_asset ON asset_storage_locations(asset_id,role,is_primary DESC,id);
CREATE INDEX ix_asset_storage_locations_health ON asset_storage_locations(health,provider_id,asset_id);
CREATE INDEX ix_asset_storage_locations_hash ON asset_storage_locations(sha256) WHERE sha256 IS NOT NULL;

CREATE TABLE storage_verification_events(
    id INTEGER PRIMARY KEY,
    public_id TEXT NOT NULL UNIQUE,
    storage_location_id INTEGER NOT NULL REFERENCES asset_storage_locations(id) ON DELETE CASCADE,
    previous_health TEXT,
    observed_health TEXT NOT NULL,
    observed_size INTEGER,
    observed_modified_at_us INTEGER,
    observed_sha256 TEXT,
    detail TEXT,
    verified_at_us INTEGER NOT NULL
);
CREATE INDEX ix_storage_verification_events_location ON storage_verification_events(storage_location_id,verified_at_us DESC);

CREATE VIEW asset_storage_overview AS
SELECT a.id AS asset_id,
       a.public_id AS asset_public_id,
       COALESCE(p.policy,
         CASE WHEN SUM(CASE WHEN f.storage_mode='managed' AND f.role='original' THEN 1 ELSE 0 END)>0
                   AND SUM(CASE WHEN f.storage_mode='referenced' THEN 1 ELSE 0 END)>0 THEN 'hybrid'
              WHEN SUM(CASE WHEN f.storage_mode='managed' AND f.role='original' THEN 1 ELSE 0 END)>0 THEN 'managed'
              ELSE 'referenced' END) AS policy,
       SUM(CASE WHEN l.role='source' THEN 1 ELSE 0 END) AS source_count,
       SUM(CASE WHEN l.role='aperture_master' THEN 1 ELSE 0 END) AS master_count,
       SUM(CASE WHEN l.health='available' THEN 1 ELSE 0 END) AS available_count
FROM assets a
LEFT JOIN asset_storage_policies p ON p.asset_id=a.id
LEFT JOIN file_instances f ON f.asset_id=a.id
LEFT JOIN asset_storage_locations l ON l.asset_id=a.id
GROUP BY a.id,a.public_id,p.policy;
"""

MIGRATION = Migration(27, "build28_flexible_storage_architecture", SQL)
