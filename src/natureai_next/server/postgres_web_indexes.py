"""PostgreSQL access paths for bounded managed-web collection queries.

WEB-053 is intentionally an index review, not a domain migration. Existing repositories
continue to own tables, constraints, and canonical identity. This module only adds
non-destructive access paths that match established managed-web query order/filter
shapes after those repositories have bootstrapped their schemas.
"""

from __future__ import annotations

from typing import Any

from natureai_next.server import (
    postgres_media,
    postgres_project_management,
    postgres_science,
)


_PROJECT_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_pm_projects_org_updated_keyset_pg "
    "ON pm_projects(organization_id,updated_at_us DESC,project_id)",
)

_MEDIA_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_governed_media_org_keyset_pg "
    "ON governed_media(organization_id,media_id DESC)",
    "CREATE INDEX IF NOT EXISTS ix_governed_media_org_mime_keyset_pg "
    "ON governed_media(organization_id,mime_type,media_id DESC)",
)

_SCIENCE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_science_observation_status_keyset_pg "
    "ON science_records(collection_name,(payload_json->>'status'),updated_at_us,record_id)",
)


def managed_web_postgres_index_statements() -> tuple[str, ...]:
    """Expose the reviewed, non-destructive WEB-053 index contract for certification."""

    return _PROJECT_INDEXES + _MEDIA_INDEXES + _SCIENCE_INDEXES


def _apply(connect: Any, statements: tuple[str, ...]) -> None:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ("fieldora_managed_web_indexes_v1",),
            )
            for statement in statements:
                cursor.execute(statement)


def ensure_managed_web_postgres_indexes(
    *, project_management: object, media: object, science: object
) -> None:
    """Install only indexes relevant to actual PostgreSQL managed-web adapters.

    SQLite repositories and narrow unit fakes deliberately no-op. Identity/link
    uniqueness remains in the media repositories: WEB-053 must not turn an access-path
    review into a destructive uniqueness migration over existing deployments.
    """

    if isinstance(
        project_management,
        postgres_project_management.PostgresProjectManagementService,
    ):
        _apply(project_management._connect, _PROJECT_INDEXES)

    metadata = getattr(media, "_metadata", None)
    if isinstance(metadata, postgres_media.PostgresMediaMetadataRepository):
        _apply(metadata._connect, _MEDIA_INDEXES)

    if isinstance(science, postgres_science.PostgresScienceRepository):
        _apply(science._connect, _SCIENCE_INDEXES)
