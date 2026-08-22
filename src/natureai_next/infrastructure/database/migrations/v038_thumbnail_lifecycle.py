"""Explicit thumbnail lifecycle for imported photo files."""

from natureai_next.infrastructure.database.migrations.core import Migration

SQL = r"""
ALTER TABLE file_instances ADD COLUMN thumbnail_state TEXT NOT NULL DEFAULT 'initial'
    CHECK(thumbnail_state IN ('initial','imported','processing','ready'));

UPDATE file_instances
SET thumbnail_state = CASE
    WHEN EXISTS(
        SELECT 1 FROM derivative_cache_entries d
        WHERE d.source_file_instance_id=file_instances.id
          AND d.derivative_kind='thumbnail' AND d.state='valid'
    ) THEN 'ready'
    WHEN EXISTS(
        SELECT 1 FROM image_properties ip
        WHERE ip.file_instance_id=file_instances.id
    ) THEN 'imported'
    ELSE 'initial'
END;

CREATE INDEX ix_file_instances_thumbnail_state
    ON file_instances(thumbnail_state,id);
"""

MIGRATION = Migration(38, "explicit thumbnail lifecycle", SQL)
