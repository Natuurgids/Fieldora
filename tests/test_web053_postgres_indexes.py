from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from natureai_next.server.postgres_media import PostgresMediaMetadataRepository
from natureai_next.server.postgres_project_management import PostgresProjectManagementService
from natureai_next.server.postgres_science import PostgresScienceRepository
from natureai_next.server.postgres_web_indexes import (
    ensure_managed_web_postgres_indexes,
    managed_web_postgres_index_statements,
)


class _Cursor:
    def __init__(self, executed: list[tuple[str, tuple[object, ...]]]) -> None:
        self.executed = executed

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def execute(self, statement: str, params: tuple[object, ...] = ()) -> None:
        self.executed.append((statement, params))


class _Connection:
    def __init__(self, executed: list[tuple[str, tuple[object, ...]]]) -> None:
        self.executed = executed

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def cursor(self) -> _Cursor:
        return _Cursor(self.executed)


def _postgres_instance(kind, executed):
    instance = object.__new__(kind)
    instance._connect = lambda: _Connection(executed)
    return instance


def test_web053_applies_only_non_destructive_indexes_to_postgres_adapters() -> None:
    executed: list[tuple[str, tuple[object, ...]]] = []
    projects = _postgres_instance(PostgresProjectManagementService, executed)
    metadata = _postgres_instance(PostgresMediaMetadataRepository, executed)
    science = _postgres_instance(PostgresScienceRepository, executed)

    ensure_managed_web_postgres_indexes(
        project_management=projects,
        media=SimpleNamespace(_metadata=metadata),
        science=science,
    )

    statements = managed_web_postgres_index_statements()
    applied = tuple(statement for statement, _params in executed if statement in statements)
    assert applied == statements
    assert all(" UNIQUE " not in f" {statement.upper()} " for statement in statements)
    assert sum("pg_advisory_xact_lock" in statement for statement, _ in executed) == 3


def test_web053_indexes_match_bounded_managed_web_query_shapes() -> None:
    statements = "\n".join(managed_web_postgres_index_statements())
    assert "pm_projects(organization_id,updated_at_us DESC,project_id)" in statements
    assert "governed_media(organization_id,media_id DESC)" in statements
    assert "governed_media(organization_id,mime_type,media_id DESC)" in statements
    assert (
        "science_records(collection_name,(payload_json->>'status'),updated_at_us,record_id)"
        in statements
    )

    root = Path(__file__).resolve().parents[1]
    pagination = (root / "src/natureai_next/server/pagination.py").read_text(encoding="utf-8")
    filtering = (root / "src/natureai_next/server/filtering.py").read_text(encoding="utf-8")
    assert "ORDER BY updated_at_us DESC,project_id LIMIT %s" in pagination
    assert "ORDER BY media_id DESC LIMIT %s" in pagination
    assert "payload_json->>'status' IN" in filtering


def test_web053_preserves_existing_media_identity_and_link_constraints() -> None:
    root = Path(__file__).resolve().parents[1]
    media = (root / "src/natureai_next/server/postgres_media.py").read_text(encoding="utf-8")
    links = (root / "src/natureai_next/server/media_links.py").read_text(encoding="utf-8")
    staged = (root / "src/natureai_next/server/staged_ingestion.py").read_text(encoding="utf-8")

    assert "ux_governed_media_managed_instance_pg" in media
    assert "ux_governed_media_referenced_source_pg" in media
    assert "_lock_content_identity" in media
    assert "PRIMARY KEY(media_id,association_type,target_id)" in links
    assert "ix_governed_media_associations_target_pg" in links
    assert '"""SQLite reference store; PostgreSQL may implement the same state contract."""' in staged
