"""Aperture-owned canonical enrichment database.

Integrations produce results, but this database remains readable and useful when
those integrations are disabled or removed.
"""

from __future__ import annotations

from pathlib import Path

from natureai_next.infrastructure.database.migrations.core import Migration
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseDescriptor

_ENRICHMENT_SQL = r"""
CREATE TABLE enrichment_records(
    enrichment_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL CHECK(subject_type IN ('asset','observation','collection','note','photo','sound','video','document')),
    subject_public_id TEXT NOT NULL,
    enrichment_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK(schema_version>=1),
    producer_id TEXT NOT NULL,
    producer_version TEXT,
    producer_run_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('generated','reviewed','pending_review','accepted','rejected','superseded','expired')),
    confidence REAL CHECK(confidence IS NULL OR (confidence>=0 AND confidence<=1)),
    summary TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(payload_json)),
    evidence_json TEXT CHECK(evidence_json IS NULL OR json_valid(evidence_json)),
    source_id TEXT,
    source_snapshot_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(source_snapshot_json)),
    created_at_us INTEGER NOT NULL,
    updated_at_us INTEGER NOT NULL,
    reviewed_at_us INTEGER,
    reviewer TEXT
);
CREATE TABLE enrichment_values(
    enrichment_id TEXT NOT NULL REFERENCES enrichment_records(enrichment_id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,
    value_ordinal INTEGER NOT NULL DEFAULT 0,
    value_type TEXT NOT NULL CHECK(value_type IN ('text','integer','real','boolean','timestamp','reference','json')),
    text_value TEXT,
    integer_value INTEGER,
    real_value REAL,
    boolean_value INTEGER CHECK(boolean_value IS NULL OR boolean_value IN(0,1)),
    timestamp_value_us INTEGER,
    reference_value TEXT,
    json_value TEXT CHECK(json_value IS NULL OR json_valid(json_value)),
    unit TEXT,
    language_code TEXT,
    confidence REAL CHECK(confidence IS NULL OR (confidence>=0 AND confidence<=1)),
    PRIMARY KEY(enrichment_id,field_key,value_ordinal)
);
CREATE TABLE enrichment_labels(
    enrichment_id TEXT NOT NULL REFERENCES enrichment_records(enrichment_id) ON DELETE CASCADE,
    label_namespace TEXT NOT NULL,
    label_key TEXT NOT NULL,
    display_value TEXT,
    value_ordinal INTEGER NOT NULL DEFAULT 0,
    confidence REAL CHECK(confidence IS NULL OR (confidence>=0 AND confidence<=1)),
    source TEXT,
    PRIMARY KEY(enrichment_id,label_namespace,label_key,value_ordinal)
);
CREATE INDEX idx_enrichment_subject ON enrichment_records(subject_type,subject_public_id,updated_at_us DESC);
CREATE INDEX idx_enrichment_type ON enrichment_records(enrichment_type,status,updated_at_us DESC);
CREATE INDEX idx_enrichment_labels_lookup ON enrichment_labels(label_namespace,label_key);
CREATE INDEX idx_enrichment_values_lookup ON enrichment_values(field_key,value_type);

CREATE TABLE source_records(
    source_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('capability','source')),
    display_name TEXT NOT NULL,
    version TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('installed','offline','removed','missing','superseded','inactive','requires_download','update_available')),
    licence TEXT,
    attribution TEXT,
    checksum TEXT,
    created_at_us INTEGER NOT NULL,
    updated_at_us INTEGER NOT NULL
);
CREATE TABLE enrichment_review_events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrichment_id TEXT NOT NULL REFERENCES enrichment_records(enrichment_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('accepted','rejected')),
    reviewer TEXT NOT NULL,
    reviewed_at_us INTEGER NOT NULL
);
CREATE INDEX idx_enrichment_source ON enrichment_records(source_id,status,updated_at_us DESC);
CREATE INDEX idx_review_events_enrichment ON enrichment_review_events(enrichment_id,reviewed_at_us DESC);

CREATE TABLE observation_subject_links(
    observation_public_id TEXT NOT NULL,
    subject_type TEXT NOT NULL CHECK(subject_type IN ('photo','sound','video','document')),
    subject_public_id TEXT NOT NULL,
    created_at_us INTEGER NOT NULL,
    PRIMARY KEY(observation_public_id,subject_type,subject_public_id)
);
CREATE INDEX idx_observation_subject_links_subject
    ON observation_subject_links(subject_type,subject_public_id,observation_public_id);
"""

MIGRATIONS = (Migration(1, "canonical enrichment store", _ENRICHMENT_SQL),)


def enrichment_descriptor(database_path: Path) -> SubsystemDatabaseDescriptor:
    return SubsystemDatabaseDescriptor("enrichment", database_path, MIGRATIONS, optional=False)


# V4 lifecycle metadata is deliberately additive so existing libraries remain readable.
_LIFECYCLE_SQL = r"""
CREATE TABLE IF NOT EXISTS source_installations(
    source_id TEXT PRIMARY KEY REFERENCES source_records(source_id) ON DELETE CASCADE,
    runtime_path TEXT,
    index_path TEXT,
    replacement_source_id TEXT REFERENCES source_records(source_id),
    last_verified_at_us INTEGER,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS source_lifecycle_events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    action TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT,
    details_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(details_json)),
    created_at_us INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_lifecycle_events_source
    ON source_lifecycle_events(source_id,created_at_us DESC);
"""


_DEPENDENCY_SQL = r"""
CREATE TABLE IF NOT EXISTS source_dependencies(
    source_id TEXT NOT NULL REFERENCES source_records(source_id) ON DELETE CASCADE,
    depends_on_source_id TEXT NOT NULL REFERENCES source_records(source_id) ON DELETE RESTRICT,
    PRIMARY KEY(source_id,depends_on_source_id),
    CHECK(source_id <> depends_on_source_id)
);
CREATE INDEX IF NOT EXISTS idx_source_dependencies_target
    ON source_dependencies(depends_on_source_id,source_id);
"""

_REVIEW_ASSIGNMENT_SQL = r"""
CREATE TABLE IF NOT EXISTS enrichment_review_assignments(
    enrichment_id TEXT PRIMARY KEY REFERENCES enrichment_records(enrichment_id) ON DELETE CASCADE,
    assigned_to TEXT NOT NULL,
    assigned_by TEXT NOT NULL,
    assigned_at_us INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_enrichment_review_assignment_user
    ON enrichment_review_assignments(assigned_to,assigned_at_us DESC);
CREATE TABLE IF NOT EXISTS enrichment_review_assignment_events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrichment_id TEXT NOT NULL,
    assigned_to TEXT,
    assigned_by TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('assigned','reassigned','unassigned','completed')),
    note TEXT NOT NULL DEFAULT '',
    created_at_us INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_enrichment_review_assignment_events
    ON enrichment_review_assignment_events(enrichment_id,created_at_us DESC);
"""
MIGRATIONS = (
    Migration(1, "canonical enrichment store", _ENRICHMENT_SQL),
    Migration(2, "source lifecycle recovery metadata", _LIFECYCLE_SQL),
    Migration(3, "source dependency safeguards", _DEPENDENCY_SQL),
    Migration(4, "assigned enrichment review queues", _REVIEW_ASSIGNMENT_SQL),
)
